
import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.config import settings
from app.core.database import async_session_factory, TaskModel, TaskEventModel, TaskResultModel, HumanInterventionModel, engine, init_db
from app.core.state_machine import TaskStatus, validate_task_transition, HumanInterventionStatus, HumanInterventionType
from app.core.redis import redis_client

from app.browser.session_manager import session_manager
from app.browser.observer import observer
from app.browser.executor import executor

from app.agent.url_guard import url_guard
from app.agent.planner import DecisionEngine
from app.agent.code_generator import PlaywrightCodeGenerator
from app.agent.validator import code_validator
from app.agent.recovery import RecoveryEngine
from app.agent.goal_verifier import GoalVerifier
from app.agent.state import diff_states
from app.agent.reporter import result_reporter

from app.captcha.sentinel import captcha_sentinel
from app.human_loop.controller import human_controller
from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider

logger = logging.getLogger("web_agent.task_manager")


class FormResponseMapping(BaseModel):
    values: Dict[str, str] = Field(default_factory=dict)


class TaskManager:
    """
    Central Coordinator for Nexagent Tasks.
    Supports pause/resume controls, Google pre-navigation, and persistent session management.
    """

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or create_llm_provider()
        self.decision_engine = DecisionEngine(self.llm_provider)
        self.code_generator = PlaywrightCodeGenerator(self.llm_provider)
        self.goal_verifier = GoalVerifier(self.llm_provider)
        self.recovery_engine = RecoveryEngine(self.llm_provider)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.paused_tasks: Set[str] = set()
        self.ws_broadcast_callback = None

    def set_ws_broadcast_callback(self, callback):
        self.ws_broadcast_callback = callback

    @staticmethod
    def _database_safe(value: Any) -> Any:
        if isinstance(value, str):
            return value.encode("cp1252", errors="replace").decode("cp1252")
        if isinstance(value, dict):
            return {TaskManager._database_safe(key): TaskManager._database_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [TaskManager._database_safe(item) for item in value]
        if isinstance(value, tuple):
            return tuple(TaskManager._database_safe(item) for item in value)
        return value

    @staticmethod
    def _editable_form_fields(state: Dict[str, Any]) -> List[Dict[str, Any]]:
        elements = state.get("interactive_elements", [])
        return [
            el for el in elements
            if el.get("tag") in {"input", "textarea", "select"}
            or el.get("role") in {"textbox", "combobox", "spinbutton", "searchbox", "listbox"}
            or el.get("contenteditable") is True
        ]

    @staticmethod
    def _missing_form_fields(state: Dict[str, Any]) -> List[Dict[str, Any]]:
        elements = state.get("interactive_elements", [])
        missing = []
        for el in elements:
            if not (
                el.get("tag") in {"input", "textarea", "select"}
                or el.get("role") in {"textbox", "combobox", "spinbutton", "searchbox", "listbox"}
                or el.get("contenteditable") is True
            ):
                continue
            if el.get("disabled") or el.get("readonly"):
                continue
            if (el.get("type") or "text").lower() in {"hidden", "button", "submit", "reset"}:
                continue
            is_required = el.get("required") or el.get("aria_required") or el.get("invalid")
            if not is_required:
                continue
            val = str(el.get("value") or "").strip()
            if not val:
                missing.append(el)
        return missing

    @staticmethod
    def _require_semantic_observation(browser_state: Dict[str, Any]) -> None:
        if browser_state.get("is_closed"):
            return
        semantic_dom = browser_state.get("semantic_dom_snapshot")
        if (
            not isinstance(semantic_dom, str)
            or not semantic_dom.strip()
            or not semantic_dom.lstrip().startswith("<semantic_dom>")
            or not semantic_dom.rstrip().endswith("</semantic_dom>")
            or not semantic_dom.strip()[len("<semantic_dom>"):-len("</semantic_dom>")].strip()
        ):
            raise RuntimeError("Observation failed: semantic DOM is missing, empty, or invalid.")

    async def _resolve_form_input(
        self,
        task_id: str,
        session,
        fields: List[Dict[str, Any]],
        suggested_value: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        goal: Optional[str] = None,
        mapping_fields: Optional[List[Dict[str, Any]]] = None,
        goal_values_source: Optional[str] = None,
    ) -> bool:
        if not fields:
            return False
        field = fields[0]
        context = context or {}
        if context.get("require_exact_choice"):
            field = dict(field)
            field["options"] = [
                {
                    "ref": item.get("ref"),
                    "label": self._human_form_field_label(item),
                    "value": item.get("value") or self._human_form_field_label(item),
                }
                for item in fields
                if item.get("ref")
            ]
            fields = [field if item.get("ref") == field.get("ref") else item for item in fields]
        base_prompt = (
            f"I found {suggested_value} in the browser. Should I fill it in {self._human_form_field_label(field)}?"
            if suggested_value
            else "Please provide the missing information needed to continue: "
            + ", ".join(self._human_form_field_label(item) for item in fields)
            + "."
        )
        if context.get("require_exact_choice"):
            available_choices = ", ".join(
                self._human_form_field_label(item)
                for item in fields
            )
            base_prompt = (
                f"Please provide the value for '{context.get('requirement') or self._human_form_field_label(field)}' "
                "in your own words. I will analyze your reply and apply it to the current form field. "
                f"Available choices are: {available_choices}. "
                "For a matrix, mention each row and its selected choice."
            )
        if field.get("validation_message"):
            base_prompt = f"{base_prompt} {field['validation_message']}"

        live_fields = {str(item.get("ref")): item for item in fields if item.get("ref")}
        response_fields = mapping_fields or fields

        if goal:
            mapping_goal = goal_values_source if goal_values_source is not None else goal
            goal_values = {}
            if self.llm_provider:
                goal_values = await self._map_form_response(mapping_goal, response_fields)
            if await self._apply_form_values(task_id, session, response_fields, goal_values):
                await self._update_task_status(task_id, TaskStatus.RUNNING)
                return True

        for attempt in range(1, 4):
            prompt = base_prompt
            if attempt > 1:
                prompt = (
                    f"I could not match the previous answer to the live form. "
                    f"Please try again (attempt {attempt} of 3) and provide an exact or clearly described "
                    f"value for {self._human_form_field_label(field)}.\n{base_prompt}"
                )
            await self._update_task_status(task_id, TaskStatus.WAITING_FOR_HUMAN)
            intervention = await self._create_intervention(
                task_id=task_id,
                intervention_type=HumanInterventionType.FORM_INPUT_REQUIRED,
                prompt=prompt,
                action_payload={
                    "fields": fields,
                    "active_field": field,
                    "suggested_value": suggested_value,
                    "context": context,
                    "attempt": attempt,
                    "max_attempts": 3,
                }
            )
            await self._broadcast(task_id, "FORM_INPUT_REQUIRED", {
                "intervention_id": intervention.get("id"),
                "created_at": intervention.get("created_at"),
                "prompt": prompt,
                "fields": fields,
                "active_field": field,
                "suggested_value": suggested_value,
                "attempt": attempt,
                "max_attempts": 3,
            })
            resolution = await human_controller.wait_for_resolution(task_id)
            if resolution.get("status") != HumanInterventionStatus.APPROVED.value:
                return False

            response_data = resolution.get("user_response") or {}
            response_text = str(response_data.get("text") or "").strip()
            logger.info(
                "Received form response for task %s: active_field=%s response_length=%s mapping_fields=%s",
                task_id,
                field.get("ref"),
                len(response_text),
                len(response_fields),
            )
            mapped_values = await self._map_form_response(response_text, response_fields)
            logger.info("Mapped form response for task %s: refs=%s", task_id, list(mapped_values))
            if not mapped_values:
                continue

            filled = await self._apply_form_values(task_id, session, response_fields, mapped_values, attempt)
            logger.info("Applied form response for task %s: filled=%s", task_id, filled)
            if filled:
                await self._update_task_status(task_id, TaskStatus.RUNNING)
                return True
        logger.warning("Form input was not resolved after 3 user attempts for task %s.", task_id)
        return False

    @staticmethod
    def _human_form_field_label(field: Dict[str, Any]) -> str:
        """Return a human-readable field label for use in user-facing prompts."""
        for key in ("label", "aria_label", "name", "placeholder"):
            value = str(field.get(key) or "").strip()
            if value and value.casefold() not in {"div", "input", "select", "textarea"}:
                return value
        context = str(field.get("form_context") or "").strip()
        if context:
            return context.split("*")[0].strip() or context
        text = str(field.get("text") or "").strip()
        if text and text.casefold() not in {"div", "input", "select", "textarea"}:
            return text
        role = str(field.get("role") or "").casefold()
        return {
            "radio": "choice",
            "checkbox": "checkbox selection",
            "switch": "toggle",
            "option": "dropdown choice",
            "combobox": "dropdown value",
            "textbox": "text value",
        }.get(role, "form field")

    async def _apply_form_values(
        self,
        task_id: str,
        session,
        fields: List[Dict[str, Any]],
        mapped_values: Dict[str, str],
        attempt: int = 0,
    ) -> int:
        live_fields = {str(item.get("ref")): item for item in fields if item.get("ref")}
        filled = 0
        for ref, mapped_value in mapped_values.items():
            live_field = live_fields.get(str(ref))
            if not live_field or not str(mapped_value).strip():
                continue
            normalized_value = str(mapped_value).strip()
            if not normalized_value:
                continue
            try:
                locator = session.page.locator(f'[data-agent-ref="{ref}"]').first
                if live_field.get("tag") == "select":
                    options = live_field.get("options") or []
                    option = next(
                        (
                            item for item in options
                            if str(item.get("value")) == normalized_value
                            or str(item.get("label", "")).casefold() == normalized_value.casefold()
                        ),
                        None,
                    )
                    if not option:
                        continue
                    await locator.select_option(value=str(option.get("value") or ""))
                elif live_field.get("role") in {"radio", "checkbox", "switch", "option", "label"}:
                    role = str(live_field.get("role") or "").casefold()
                    if role in {"checkbox", "switch"}:
                        desired = normalized_value.casefold() in {"true", "1", "yes", "y", "on", "checked", "haan", "han"}
                        current = live_field.get("checked") is True or live_field.get("aria_checked") is True or live_field.get("selected_state") is True
                        if desired != current:
                            await locator.click()
                    else:
                        is_dropdown_trigger = (
                            role == "option"
                            and not live_field.get("expanded")
                            and (live_field.get("has_popup") or live_field.get("controls"))
                        )
                        if is_dropdown_trigger:
                            await locator.click()
                            option_locator = session.page.get_by_role("option", name=normalized_value, exact=True)
                            if await option_locator.count() == 1:
                                await option_locator.click()
                        else:
                            await locator.click()
                else:
                    await locator.fill(normalized_value)
                    if hasattr(locator, "input_value"):
                        actual_value = await locator.input_value()
                        if actual_value != normalized_value:
                            logger.warning("Live form value was not retained for %s.", ref)
                            continue
            except Exception as error:
                logger.warning("Could not apply form value for %s on attempt %s: %s", ref, attempt, error)
                continue
            filled += 1
        return filled

    async def _resolve_file_upload(self, task_id: str, session, target: Dict[str, Any]) -> bool:
        upload_mode = "folder" if str(target.get("upload_mode") or "file").casefold() == "folder" else "file"
        field = {
            "ref": target.get("ref"),
            "label": target.get("field_label") or target.get("label") or "file upload",
            "type": "file",
            "tag": "input",
        }
        if not field["ref"]:
            return False
        item_name = "folder" if upload_mode == "folder" else "file"
        prompt = f"Please select and upload the required {item_name} for {field['label']}, then continue."
        for attempt in range(1, 4):
            attempt_prompt = prompt if attempt == 1 else (
                f"No {item_name} was detected in Chromium. In the Chromium browser, click Add file, "
                f"select the required {item_name} for {field['label']}, then click Continue "
                f"(attempt {attempt} of 3)."
            )
            if attempt == 1:
                attempt_prompt = (
                    f"In the Chromium browser, click the '{field['label']}' upload control, "
                    f"select the required {item_name}, close the native dialog, then click Continue here."
                )
            await self._update_task_status(task_id, TaskStatus.WAITING_FOR_HUMAN)
            await self._create_intervention(
                task_id=task_id,
                intervention_type=HumanInterventionType.FILE_UPLOAD_REQUIRED,
                prompt=attempt_prompt,
                action_payload={
                    "field": field,
                    "upload_mode": upload_mode,
                    "attempt": attempt,
                    "max_attempts": 3,
                },
            )
            await self._broadcast(task_id, "FILE_UPLOAD_REQUIRED", {
                "prompt": attempt_prompt,
                "field": field,
                "upload_mode": upload_mode,
                "attempt": attempt,
                "max_attempts": 3,
            })
            resolution = await human_controller.wait_for_resolution(task_id)
            if resolution.get("status") != HumanInterventionStatus.APPROVED.value:
                return False
            response_data = resolution.get("user_response") or {}
            file_paths = response_data.get("file_paths") or []
            if file_paths:
                file_inputs = session.page.locator('input[type="file"]')
                if await file_inputs.count():
                    await file_inputs.first.set_input_files(file_paths)
            if await self._file_upload_is_ready(session, field):
                await self._update_task_status(task_id, TaskStatus.RUNNING)
                return True
        logger.warning("No file selected after 3 Chromium upload attempts for task %s.", task_id)
        return False

    @staticmethod
    async def _file_upload_is_ready(session, field: Dict[str, Any]) -> bool:
        """Accept native file inputs and custom browser upload widgets."""
        for frame in session.page.frames:
            file_inputs = frame.locator('input[type="file"]')
            if await file_inputs.count():
                selected_count = await file_inputs.evaluate_all(
                    "inputs => inputs.reduce((count, input) => count + (input.files ? input.files.length : 0), 0)"
                )
                if selected_count:
                    return True

        ref = str(field.get("ref") or "")
        if not ref:
            return False
        locator = session.page.locator(f'[data-agent-ref="{ref}"]').first
        if await locator.count() == 0:
            return False
        upload_text = await locator.evaluate(
            "element => (element.closest('[role=listitem], fieldset, [role=group]') || element.parentElement || element).innerText || ''"
        )
        normalized = str(upload_text or "").casefold()
        return bool(
            re.search(r"\b(remove|change|replace|uploaded|selected|attached)\b", normalized)
            or re.search(r"\b[^\s]+\.(pdf|docx?|xlsx?|png|jpe?g|zip)\b", normalized)
        )

    async def _map_form_response(self, response_text: str, fields: List[Dict[str, Any]]) -> Dict[str, str]:
        if not response_text or not fields:
            return {}
        if not self.llm_provider:
            return {}
        field_context = [
            {
                "ref": field.get("ref"),
                "label": field.get("label"),
                "type": field.get("type"),
                "role": field.get("role"),
                "name": field.get("name"),
                "placeholder": field.get("placeholder"),
                "value": field.get("value"),
                "checked": field.get("checked"),
                "selected": field.get("selected"),
                "required": field.get("required") or field.get("aria_required"),
                "validation_message": field.get("validation_message"),
                "form_context": field.get("form_context"),
                "options": field.get("options") or [],
            }
            for field in fields
        ]
        try:
            result = await self.llm_provider.generate_structured(
                system_prompt=(
                    "Analyze the user's natural-language goal or response against the provided current DOM form fields. "
                    "Understand any user format or language, including English, Urdu, Roman Urdu, Hindi, mixed language, "
                    "casual wording, punctuation, capitalization, numbering, comma-separated answers, and multiple answers. "
                    "Return only values explicitly stated or unambiguously named by the user and present in the "
                    "current DOM. Use the exact live field refs as keys. Never invent, guess, infer, or duplicate "
                    "values. For radio, checkbox, switch, and option controls, map each named choice to its own "
                    "field ref. For select fields, return the exact option value or label from options. "
                    "For checkboxes and switches, return true/false based only on explicit yes/no wording. "
                    "Normalize dates to a value accepted by the live input type when the user gives a clear date. "
                    "Ignore unrelated words and do not fill fields the user did not answer."
                ),
                user_prompt=(
                    "CURRENT FORM FIELDS (authoritative live DOM):\n"
                    f"{field_context}\n\nUSER'S NATURAL GOAL OR RESPONSE:\n{response_text}\n\n"
                    "Return the JSON mapping only."
                ),
                response_model=FormResponseMapping,
                temperature=0.0,
            )
            values = result.get("values", {}) if isinstance(result, dict) else {}
            if not isinstance(values, dict):
                return {}
            live_refs = {str(field.get("ref")): field for field in fields if field.get("ref")}
            normalized_values = {}
            for key, value in values.items():
                key_text = str(key).strip()
                if key_text in live_refs:
                    normalized_values[key_text] = str(value)
                    continue
                key_lower = key_text.casefold()
                matching_field = next(
                    (
                        field for field in fields
                        if key_lower in {
                            str(field.get("label") or "").casefold().strip(),
                            str(field.get("name") or "").casefold().strip(),
                        }
                    ),
                    None,
                )
                if matching_field and matching_field.get("ref"):
                    normalized_values[str(matching_field["ref"])] = str(value)
            return {ref: value for ref, value in normalized_values.items() if value.strip()}
        except Exception as error:
            logger.warning("Could not map human form response to current fields: %s", error)
            return {}

    async def _google_account_is_authenticated(self, session) -> bool:
        """
        Comprehensive check to determine whether a Google account is logged in.
        Checks browser cookies, current URL, and DOM elements on Google.
        """
        try:
            current_url = (session.page.url or "").lower()

            # Active sign-in / challenge page markers mean NOT authenticated
            if "accounts.google.com" in current_url and any(
                marker in current_url for marker in ("signin", "identifier", "challenge", "servicelogin", "speedbump", "v3/signin")
            ):
                return False

            if "myaccount.google.com" in current_url:
                return True

            # 1. Check browser context cookies for Google session auth tokens
            has_auth_cookie = False
            try:
                cookies = await session.context.cookies(["https://www.google.com", "https://accounts.google.com"])
                google_auth_cookies = {"SID", "SSID", "HSID", "__Secure-1PSID", "__Secure-3PSID", "SAPISID"}
                has_auth_cookie = any(
                    c.get("name") in google_auth_cookies and bool(c.get("value"))
                    for c in cookies
                )
            except Exception as cookie_err:
                logger.debug("Could not inspect cookies for Google auth check: %s", cookie_err)

            # 2. If currently on google.com or accounts.google.com, inspect the live DOM
            if "google." in current_url or "accounts.google.com" in current_url:
                # Dismiss cookie consent modal if visible
                try:
                    consent_btn = session.page.locator(
                        'button:has-text("Accept all"), button:has-text("I agree"), button:has-text("Reject all"), div[role="dialog"] button:has-text("Accept")'
                    ).first
                    if await consent_btn.count() > 0 and await consent_btn.is_visible():
                        await consent_btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                # Check for Google Account profile/avatar indicators
                avatar_locator = session.page.locator(
                    'a[href*="SignOutOptions"], [aria-label*="Google Account"], a[href*="ManageAccount"], a[href*="myaccount.google.com"], #gb a[href*="SignOutOptions"], img[alt*="Google Account"]'
                )
                if await avatar_locator.count() > 0:
                    return True

                # Check for explicit Sign in button
                signin_locator = session.page.locator(
                    'a[href*="accounts.google.com/ServiceLogin"], a[href*="ServiceLogin"], a[aria-label*="Sign in"], a:has-text("Sign in"), a:has-text("Sign In")'
                )
                if await signin_locator.count() > 0:
                    return False

            # Fall back to auth cookie presence
            return has_auth_cookie
        except Exception as e:
            logger.warning("Error verifying Google account authentication: %s", e)
            return False

    @staticmethod
    def _is_google_authentication_page(url: str) -> bool:
        normalized_url = (url or "").casefold()
        return (
            "accounts.google.com" in normalized_url
            and any(marker in normalized_url for marker in ("signin", "challenge", "servicelogin", "accountchooser"))
        ) or "myaccount.google.com/verification" in normalized_url

    async def _dismiss_google_consent(self, session) -> None:
        """Dismiss Google cookie/consent dialog if visible."""
        try:
            consent_btn = session.page.locator(
                'button:has-text("Accept all"), button:has-text("I agree"), button:has-text("Reject all"), div[role="dialog"] button:has-text("Accept")'
            ).first
            if await consent_btn.count() > 0 and await consent_btn.is_visible():
                await consent_btn.click()
                await asyncio.sleep(0.3)
        except Exception:
            pass

    async def _create_intervention(
        self,
        task_id: str,
        intervention_type: HumanInterventionType,
        prompt: str,
        action_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        record = human_controller.create_intervention_request(
            task_id=task_id,
            intervention_type=intervention_type,
            prompt=prompt,
            action_payload=action_payload,
        )
        try:
            async with async_session_factory() as db:
                db.add(HumanInterventionModel(
                    id=record["id"],
                    task_id=task_id,
                    intervention_type=record["intervention_type"],
                    status=record["status"],
                    prompt=self._database_safe(prompt),
                    action_payload=self._database_safe(action_payload),
                ))
                await db.commit()
        except Exception as db_err:
            logger.warning("Could not persist intervention record to DB: %s", db_err)
        return record

    async def _wait_for_account_login(self, task_id: str, session) -> bool:
        """Give the user an interactive live browser window for manual account login."""
        await self._update_task_status(task_id, TaskStatus.WAITING_FOR_HUMAN, current_url=session.page.url)
        prompt = "Please sign in to your Google Account in the Live Browser preview on the right. Once signed in, click Continue to proceed with your task."
        await self._create_intervention(
            task_id=task_id,
            intervention_type=HumanInterventionType.ACCOUNT_LOGIN_REQUIRED,
            prompt=prompt,
            action_payload={"url": session.page.url}
        )

        # Capture screenshot and base64 live frame of Google login page so it immediately shows in preview
        try:
            frame_data = await session.capture_base64_frame()
            if frame_data:
                await self._broadcast(task_id, "BROWSER_FRAME", {"frame_data": frame_data}, persist=False)
            screenshot_path = await session.capture_screenshot("google_login.png")
            await self._broadcast(task_id, "BROWSER_OBSERVED", {
                "step": 0,
                "url": session.page.url,
                "title": await session.page.title(),
                "screenshot_path": screenshot_path,
                "frame_data": frame_data,
            })
        except Exception as err:
            logger.debug("Screenshot error during login wait: %s", err)

        await self._broadcast(task_id, "ACCOUNT_LOGIN_REQUIRED", {
            "prompt": prompt,
            "url": session.page.url
        })

        resolution = await human_controller.wait_for_resolution(task_id)
        if resolution.get("status") != HumanInterventionStatus.APPROVED.value:
            return False

        # Wait briefly for page to settle after user clicks Continue
        try:
            await session.page.wait_for_load_state("domcontentloaded", timeout=5000)
            await asyncio.sleep(1.0)
        except Exception:
            pass

        # Directly navigate to Google home page once sign-in is completed
        try:
            logger.info("Directly opening Google home page post-sign-in for task %s", task_id)
            await session.page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
            await self._dismiss_google_consent(session)
        except Exception as nav_err:
            logger.warning("Navigation to google.com post-sign-in error: %s", nav_err)

        # Check and persist auth cookies if logged in
        if await self._google_account_is_authenticated(session):
            logger.info("Google Account login confirmed for task %s.", task_id)
        else:
            logger.info("User clicked Continue for task %s. Proceeding with Google open.", task_id)

        # Save cookies & storage state so Google login is remembered for this user's future tasks!
        try:
            if session.seed_path:
                await session.persist_storage_state(session.seed_path)
                logger.info("Successfully persisted isolated login state for task %s to %s.", task_id, session.seed_path)
        except Exception as e:
            logger.warning("Could not persist storage state post-login: %s", e)

        # Immediately broadcast live frame and screenshot of Google homepage so live browser preview updates
        try:
            frame_data = await session.capture_base64_frame()
            if frame_data:
                await self._broadcast(task_id, "BROWSER_FRAME", {"frame_data": frame_data}, persist=False)
            screenshot_path = await session.capture_screenshot("post_login_google.png")
            await self._broadcast(task_id, "BROWSER_OBSERVED", {
                "step": 0,
                "url": session.page.url,
                "title": await session.page.title(),
                "screenshot_path": screenshot_path,
                "frame_data": frame_data,
            })
        except Exception as err:
            logger.debug("Post-login live frame broadcast warning: %s", err)

        await self._update_task_status(task_id, TaskStatus.RUNNING, current_url=session.page.url)
        return True

    async def _broadcast(self, task_id: str, event_type: str, data: Dict[str, Any], persist: bool = True):
        payload = {
            "task_id": task_id,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data
        }
        if persist:
            history_key = f"task:{task_id}:events"
            try:
                history = await redis_client.get_json(history_key)
                if not isinstance(history, list):
                    history = []
                history.append(payload)
                await redis_client.set_json(history_key, history[-100:])
                await redis_client.set_json(f"task:{task_id}:latest_event", payload)
            except Exception as error:
                logger.warning("Could not persist task event %s for %s: %s", event_type, task_id, error)
        if self.ws_broadcast_callback:
            try:
                await self.ws_broadcast_callback(task_id, payload)
            except Exception as e:
                logger.debug(f"WS Broadcast error: {e}")

    async def _load_parent_task_context(self, parent_task_id: str) -> Dict[str, Any]:
        async with async_session_factory() as session:
            goals = []
            all_results = []
            curr_id = parent_task_id
            depth = 0
            root_parent = None

            while curr_id and depth < 5:
                stmt = (
                    select(TaskModel)
                    .where(TaskModel.id == curr_id)
                    .options(selectinload(TaskModel.result), selectinload(TaskModel.events))
                )
                res = await session.execute(stmt)
                curr_task = res.scalar_one_or_none()
                if not curr_task:
                    break
                if not root_parent:
                    root_parent = curr_task
                goals.append(curr_task.goal)
                if curr_task.result and curr_task.result.summary:
                    all_results.append({
                        "task_id": curr_task.id,
                        "goal": curr_task.goal,
                        "summary": curr_task.result.summary,
                        "data": curr_task.result.data,
                    })
                curr_id = curr_task.parent_task_id
                depth += 1

            if not root_parent:
                return {}

            goals.reverse()
            all_results.reverse()

            checkpoint = root_parent.checkpoint or {}
            step_history = list(checkpoint.get("step_history", []))
            if not step_history and root_parent.events:
                for evt in sorted(root_parent.events, key=lambda e: e.step):
                    step_history.append({
                        "step": evt.step,
                        "action": evt.event_type,
                        "intent": evt.intent,
                        "target": evt.action_payload.get("target") if evt.action_payload else {},
                        "success": evt.success,
                        "error": evt.error,
                        "user_reply": evt.action_payload.get("user_reply") if evt.action_payload else None
                    })

            return {
                "parent_task_id": root_parent.id,
                "parent_goal": root_parent.goal,
                "previous_goals": goals,
                "previous_results": all_results,
                "parent_result_summary": root_parent.result.summary if root_parent.result else None,
                "parent_extracted_data": root_parent.result.data if root_parent.result else None,
                "parent_url": root_parent.current_url,
                "step_history": step_history,
                "visited_urls": checkpoint.get("visited_urls", []),
                "execution_attempts": checkpoint.get("execution_attempts", {}),
            }

    async def create_task(
        self,
        goal: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        guest_id: Optional[str] = None,
        file_context: Optional[str] = None,
        parent_task_id: Optional[str] = None,
    ) -> str:
        async with async_session_factory() as session:
            task = TaskModel(
                goal=self._database_safe(goal),
                status=TaskStatus.CREATED.value,
                user_id=user_id,
                conversation_id=conversation_id,
                guest_id=guest_id,
                file_context=self._database_safe(file_context),
                parent_task_id=parent_task_id,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            task_id = task.id

        await self._broadcast(task_id, "TASK_CREATED", {"goal": goal, "status": TaskStatus.CREATED.value, "has_file_context": bool(file_context), "parent_task_id": parent_task_id})
        return task_id

    def start_task(self, task_id: str, goal: str, file_context: Optional[str] = None, parent_task_id: Optional[str] = None):
        loop_task = asyncio.create_task(self._run_autonomous_loop(task_id, goal, file_context=file_context, parent_task_id=parent_task_id))
        self.active_tasks[task_id] = loop_task

    async def continue_task(self, task_id: str, goal: str, file_context: Optional[str] = None, parent_task_id: Optional[str] = None) -> bool:
        if task_id in self.active_tasks:
            return False
        self.start_task(task_id, goal, file_context=file_context, parent_task_id=parent_task_id)
        return True

    async def pause_task(self, task_id: str) -> bool:
        """
        Pauses an active task execution loop.
        """
        if task_id in self.active_tasks:
            self.paused_tasks.add(task_id)
            await self._update_task_status(task_id, TaskStatus.PAUSED)
            await self._broadcast(task_id, "TASK_PAUSED", {"task_id": task_id, "message": "Task execution paused by user."})
            logger.info(f"Task {task_id} execution paused.")
            return True
        return False

    async def resume_task(self, task_id: str) -> bool:
        """
        Resumes a paused task execution loop.
        """
        if task_id in self.paused_tasks:
            self.paused_tasks.discard(task_id)
            await self._update_task_status(task_id, TaskStatus.RUNNING)
            await self._broadcast(task_id, "TASK_RESUMED", {"task_id": task_id, "message": "Task execution resumed."})
            logger.info(f"Task {task_id} execution resumed.")
            return True
        return False

    async def _wait_if_paused(self, task_id: str) -> bool:
        """
        If task is in self.paused_tasks, wait asynchronously until resumed or cancelled.
        Returns False if task was cancelled or stopped, True if running.
        """
        if task_id in self.paused_tasks:
            logger.info("Task %s entered pause wait checkpoint.", task_id)
            await self._update_task_status(task_id, TaskStatus.PAUSED)
            while task_id in self.paused_tasks:
                if task_id not in self.active_tasks:
                    logger.info("Task %s was cancelled or removed while paused.", task_id)
                    return False
                await asyncio.sleep(0.5)
            logger.info("Task %s resumed from pause checkpoint.", task_id)
        return task_id in self.active_tasks

    async def _update_task_status(self, task_id: str, status: TaskStatus, current_url: Optional[str] = None):
        # Prevent transient statuses (OBSERVING, PLANNING, RUNNING) from overriding PAUSED
        if task_id in self.paused_tasks and status not in (TaskStatus.PAUSED, TaskStatus.CANCELLED, TaskStatus.FAILED):
            logger.debug("Task %s is paused; ignoring status update to %s", task_id, status)
            return

        database_updated = False
        for attempt in range(1, 4):
            try:
                async with async_session_factory() as session:
                    db_task = await session.get(TaskModel, task_id)
                    if db_task:
                        db_task.status = status.value
                        if current_url:
                            db_task.current_url = current_url
                        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                            db_task.completed_at = datetime.utcnow()
                        await session.commit()
                database_updated = True
                break
            except Exception as exc:
                logger.warning(
                    "Database status update failed for task %s (attempt %s/3): %s",
                    task_id,
                    attempt,
                    exc,
                )
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)

        if not database_updated:
            logger.error("Could not persist status for task %s after 3 attempts; continuing task loop.", task_id)

        await redis_client.set_json(f"task:{task_id}:state", {"status": status.value, "url": current_url})
        await self._broadcast(task_id, "STATUS_CHANGE", {"status": status.value, "url": current_url})

    async def _update_task_file_context(self, task_id: str, file_context: str):
        for attempt in range(1, 4):
            try:
                async with async_session_factory() as session:
                    db_task = await session.get(TaskModel, task_id)
                    if db_task:
                        db_task.file_context = self._database_safe(file_context)
                        await session.commit()
                break
            except Exception as exc:
                logger.warning("Database file_context update failed for task %s (attempt %s/3): %s", task_id, attempt, exc)
                await asyncio.sleep(0.5)

    async def _run_autonomous_loop(self, task_id: str, goal: str, file_context: Optional[str] = None, parent_task_id: Optional[str] = None):
        logger.info(f"Starting autonomous loop for task {task_id}: '{goal}' (parent_task_id={parent_task_id})")
        start_time = datetime.utcnow()
        visited_urls: List[str] = []
        step_history: List[Dict[str, Any]] = []
        executed_fingerprints: Set[str] = set()
        execution_attempts: Dict[str, int] = {}

        async with async_session_factory() as checkpoint_session:
            checkpoint_task = await checkpoint_session.get(TaskModel, task_id)
            checkpoint = checkpoint_task.checkpoint if checkpoint_task else None
            if not parent_task_id and checkpoint_task and checkpoint_task.parent_task_id:
                parent_task_id = checkpoint_task.parent_task_id
            if not file_context and checkpoint_task and checkpoint_task.file_context:
                file_context = checkpoint_task.file_context
            owner_key = (
                f"user:{checkpoint_task.user_id}"
                if checkpoint_task and checkpoint_task.user_id
                else f"guest:{checkpoint_task.guest_id}"
                if checkpoint_task and checkpoint_task.guest_id
                else None
            )

        parent_context = {}
        if parent_task_id:
            parent_context = await self._load_parent_task_context(parent_task_id)

        if checkpoint:
            visited_urls = checkpoint.get("visited_urls", [])
            step_history = checkpoint.get("step_history", [])
            execution_attempts = checkpoint.get("execution_attempts", {})
        elif parent_context:
            visited_urls = list(parent_context.get("visited_urls", []))
            step_history = list(parent_context.get("step_history", []))
            execution_attempts = dict(parent_context.get("execution_attempts", {}))

        start_step = (checkpoint.get("step", 0) + 1) if checkpoint else 1

        await self._update_task_status(task_id, TaskStatus.PLANNING)
        frame_cb = lambda frame: self._broadcast(
            task_id,
            "BROWSER_FRAME",
            {"frame_data": frame},
            persist=False,
        )

        session = None
        is_continued_session = False
        if parent_task_id:
            session = await session_manager.adopt_session(
                parent_task_id,
                task_id,
                frame_callback=frame_cb,
            )
            if session:
                is_continued_session = True
                logger.info(
                    "Reusing active browser session for continuation task %s from parent %s (active url: %s).",
                    task_id,
                    parent_task_id,
                    session.page.url,
                )

        if not session:
            session = await session_manager.create_session(
                task_id,
                owner_key=owner_key,
                frame_callback=frame_cb,
            )

        # 1. Initialize and open Google in the browser if starting fresh
        if not is_continued_session or session.page.url in ("about:blank", ""):
            logger.info("Opening Google (https://www.google.com) for task %s", task_id)
            for attempt in range(2):
                try:
                    await session.page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=12000)
                    if session.page.url not in ("about:blank", ""):
                        break
                except Exception as nav_err:
                    logger.warning("Error navigating to Google (attempt %s): %s", attempt + 1, nav_err)
                    if attempt == 0 and getattr(session, "has_proxy", False):
                        logger.info("Proxy connection failed on Google. Retrying with direct connection for task %s...", task_id)
                        session = await session_manager.fallback_session_to_direct(
                            task_id,
                            owner_key=owner_key,
                            frame_callback=frame_cb,
                        )

            # Dismiss Google consent dialog if shown (common on EU / AWS servers)
            await self._dismiss_google_consent(session)

            # Update DB current_url so REST API and frontend immediately reflect Google
            await self._update_task_status(task_id, TaskStatus.PLANNING, current_url=session.page.url)

            # Broadcast base64 live frame and screenshot so Live Browser preview immediately shows Google
            try:
                frame_data = await session.capture_base64_frame()
                if frame_data:
                    await self._broadcast(task_id, "BROWSER_FRAME", {"frame_data": frame_data}, persist=False)
                screenshot_path = await session.capture_screenshot("initial_google.jpg")
                await self._broadcast(task_id, "BROWSER_OBSERVED", {
                    "step": 0,
                    "url": session.page.url,
                    "title": await session.page.title(),
                    "screenshot_path": screenshot_path,
                    "frame_data": frame_data,
                })
            except Exception as err:
                logger.debug("Initial screenshot broadcast warning: %s", err)

        # 2. Check if user Google Account is already logged in
        if settings.BROWSER_REQUIRE_LOGIN_BEFORE_TASK and not is_continued_session:
            try:
                is_google_logged_in = await self._google_account_is_authenticated(session)
                if is_google_logged_in:
                    logger.info("Google Account is already logged in for task %s. Proceeding with task.", task_id)
                else:
                    logger.info("Google Account is NOT logged in for task %s. User must log in before proceeding.", task_id)
                    try:
                        if not self._is_google_authentication_page(session.page.url):
                            await session.page.goto("https://accounts.google.com/", wait_until="domcontentloaded", timeout=15000)
                    except Exception as nav_err:
                        logger.warning("Error opening Google Sign In: %s", nav_err)
                        if getattr(session, "has_proxy", False):
                            logger.info("Proxy failed on Google Sign In. Retrying direct for task %s...", task_id)
                            session = await session_manager.fallback_session_to_direct(
                                task_id,
                                owner_key=owner_key,
                                frame_callback=frame_cb,
                            )
                            await session.page.goto("https://accounts.google.com/", wait_until="domcontentloaded", timeout=15000)

                    login_ok = await self._wait_for_account_login(task_id, session)
                    if not login_ok:
                        logger.warning("Google account login was not completed for task %s. Continuing with task.", task_id)
            except Exception as auth_err:
                logger.warning("Google account check encountered: %s. Continuing with task.", auth_err)

        # 3. Post-login destination routing:
        # If user provided an explicit URL in goal, navigate to it.
        # If continuing an existing live session, DO NOT navigate; stay on current page.
        # If continuing parent but browser was reopened, navigate to parent's last visited URL.
        # Otherwise, open default start URL (or keep Google).
        user_urls = url_guard.register_user_urls(task_id, goal)
        if user_urls:
            target_url = user_urls[0]
            if session.page.url != target_url:
                try:
                    logger.info("Navigating task %s to user-provided URL: %s", task_id, target_url)
                    await session.page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as nav_err:
                    logger.warning("User URL navigation error for task %s: %s", task_id, nav_err)
        elif is_continued_session and session.page.url not in ("about:blank", "") and "accounts.google.com" not in session.page.url and "myaccount.google.com" not in session.page.url:
            logger.info("Task continuation active: keeping current page at %s without reloading default URL.", session.page.url)
        elif parent_context and parent_context.get("parent_url") and parent_context.get("parent_url") not in ("about:blank", ""):
            resume_url = parent_context.get("parent_url")
            try:
                logger.info("Resuming continuation task %s at previous page: %s", task_id, resume_url)
                await session.page.goto(resume_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as nav_err:
                logger.warning("Resume URL navigation error for task %s: %s", task_id, nav_err)
        else:
            default_url = settings.BROWSER_DEFAULT_START_URL.strip() or "https://www.google.com"
            if any(m in session.page.url for m in ("accounts.google.com", "myaccount.google.com", "about:blank")) or not session.page.url:
                try:
                    logger.info("Returning to default entry URL post-auth: %s", default_url)
                    await session.page.goto(default_url, wait_until="domcontentloaded", timeout=30000)
                    await self._dismiss_google_consent(session)
                except Exception as nav_err:
                    logger.warning("Default URL navigation error for task %s: %s", task_id, nav_err)

        try:
            safety_step_limit = max(settings.MAX_TASK_STEPS, 200)
            for step in range(start_step, safety_step_limit + 1):
                # Check pause checkpoint
                if not await self._wait_if_paused(task_id):
                    return

                if not session or not session.page or session.page.is_closed():
                    logger.info("Browser session closed for task %s before step %s.", task_id, step)
                    await self._finish_task_failure(
                        task_id, goal, "Browser session was closed.", start_time, visited_urls, step
                    )
                    return

                if self._is_google_authentication_page(session.page.url):
                    if not await self._wait_for_account_login(task_id, session):
                        await self._finish_task_failure(
                            task_id,
                            goal,
                            "Google account login was not completed.",
                            start_time,
                            visited_urls,
                            step,
                        )
                        return

                await self._update_task_status(task_id, TaskStatus.OBSERVING)

                # 1. Observe fresh browser state
                browser_state = await observer.observe(session.page)
                if browser_state.get("is_closed") or session.page.is_closed():
                    logger.info("Browser session closed during observation for task %s.", task_id)
                    if task_id in self.active_tasks:
                        await self._finish_task_failure(task_id, goal, "Browser session was closed.", start_time, visited_urls, step)
                    return

                self._require_semantic_observation(browser_state)
                current_url = browser_state.get("url", "")
                if current_url and current_url not in visited_urls:
                    visited_urls.append(current_url)

                # Capture preview screenshot
                screenshot_path = await session.capture_screenshot(f"step_{step}.png")
                frame_data_snap = None
                try:
                    frame_data_snap = await session.capture_base64_frame()
                except Exception:
                    pass

                await self._broadcast(task_id, "BROWSER_OBSERVED", {
                    "step": step,
                    "url": current_url,
                    "title": browser_state.get("title"),
                    "screenshot_path": screenshot_path,
                    "frame_data": frame_data_snap,
                    "interactive_count": len(browser_state.get("interactive_elements", []))
                })

                # 2. CAPTCHA Sentinel Check
                captcha_result = captcha_sentinel.inspect_state(browser_state)
                if captcha_result["detected"]:
                    await self._update_task_status(task_id, TaskStatus.WAITING_FOR_HUMAN)
                    await self._create_intervention(
                        task_id=task_id,
                        intervention_type=HumanInterventionType.CAPTCHA,
                        prompt=captcha_result["message"]
                    )
                    await self._broadcast(task_id, "CAPTCHA_DETECTED", captcha_result)

                    resolution = await human_controller.wait_for_resolution(task_id)
                    if resolution.get("status") != HumanInterventionStatus.APPROVED.value:
                        await self._finish_task_failure(task_id, goal, "Task blocked by unresolved CAPTCHA.", start_time, visited_urls, step)
                        return

                    # Human solved/approved CAPTCHA: wait for page stabilization and re-observe fresh DOM
                    logger.info("Human intervention resolved. Waiting for browser stabilization and re-observing fresh page...")
                    await self._update_task_status(task_id, TaskStatus.RUNNING)
                    try:
                        await session.page.wait_for_load_state("domcontentloaded", timeout=15000)
                        await asyncio.sleep(1.5)
                    except Exception:
                        pass

                    # Re-observe fresh browser state post-CAPTCHA
                    browser_state = await observer.observe(session.page)
                    self._require_semantic_observation(browser_state)
                    current_url = browser_state.get("url", "")
                    if current_url and current_url not in visited_urls:
                        visited_urls.append(current_url)
                    screenshot_path = await session.capture_screenshot(f"step_{step}_resolved.png")
                    frame_data_res = None
                    try:
                        frame_data_res = await session.capture_base64_frame()
                    except Exception:
                        pass
                    await self._broadcast(task_id, "BROWSER_OBSERVED", {
                        "step": step,
                        "url": current_url,
                        "title": browser_state.get("title"),
                        "screenshot_path": screenshot_path,
                        "frame_data": frame_data_res,
                        "interactive_count": len(browser_state.get("interactive_elements", []))
                    })

                # 3. Goal Verification Check
                if step > 1 and (not step_history or step_history[-1].get("success", True)):
                    extracted_data = step_history[-1].get("extracted_data") if step_history else None
                    verification = await self.goal_verifier.verify_goal(goal, browser_state, extracted_data, step)
                    if verification.get("is_complete"):
                        await self._finish_task_success(
                            task_id=task_id,
                            goal=goal,
                            summary=verification.get("reason", "Goal successfully completed."),
                            data=verification.get("final_data", extracted_data),
                            start_time=start_time,
                            visited_urls=visited_urls,
                            action_count=step,
                            step_history=step_history,
                            current_url=session.page.url,
                        )
                        return

                # 4. Check Loop Detection
                is_loop = self.recovery_engine.detect_loop(step_history, visited_urls)
                loop_warning = None
                if is_loop:
                    await self._broadcast(task_id, "LOOP_DETECTED", {"step": step, "message": "Loop detected. Triggering recovery."})
                    recent_urls = [u for u in visited_urls[-4:]]
                    recent_intents = [str(s.get("intent") or "") for s in step_history[-4:] if s.get("intent")]
                    loop_warning = (
                        f"CRITICAL REPETITION WARNING: You have been repeating actions or oscillating between pages "
                        f"(recent URLs: {', '.join(set(recent_urls))}; recent intents: {', '.join(recent_intents[:2])}). "
                        f"You MUST NOT repeat these actions or navigate back to the same pages. "
                        f"Change your strategy dynamically: use site search to locate the item directly, "
                        f"check top-level navigation, or explore alternative links in the current DOM."
                    )

                # 5. Decide Next Action (Planning)
                if not await self._wait_if_paused(task_id):
                    return
                await self._update_task_status(task_id, TaskStatus.PLANNING)
                planning_error = None
                action_intent = None
                for planning_attempt in range(settings.MAX_ACTION_RETRIES + 1):
                    try:
                        action_intent = await self.decision_engine.decide_next_action(
                            task_id=task_id,
                            user_goal=goal,
                            browser_state=browser_state,
                            step_history=step_history,
                            visited_urls=visited_urls,
                            planning_error=planning_error,
                            file_context=file_context,
                            loop_warning=loop_warning,
                            parent_context=parent_context,
                        )
                        break
                    except RuntimeError as planner_error:
                        planning_error = str(planner_error)
                        if planning_attempt >= settings.MAX_ACTION_RETRIES:
                            logger.error(
                                "Planner failed after %s attempts at step %s; preserving session for a fresh retry: %s",
                                planning_attempt + 1,
                                step,
                                planning_error,
                            )
                            break
                        logger.warning(
                            "Planner decision rejected at step %s; requesting a new decision (%s/%s): %s",
                            step,
                            planning_attempt + 1,
                            settings.MAX_ACTION_RETRIES,
                            planning_error,
                        )

                if action_intent is None:
                    await self._broadcast(task_id, "PLANNING_RETRY_REQUIRED", {
                        "step": step,
                        "error": planning_error,
                        "message": "The AI decision was invalid. Re-observing the current page before trying again."
                    })
                    await asyncio.sleep(1.0)
                    continue

                await self._broadcast(task_id, "ACTION_PLANNED", {
                    "step": step,
                    "action": action_intent.get("action"),
                    "intent": action_intent.get("intent"),
                    "thought": action_intent.get("thought", ""),
                    "ordered_steps": action_intent.get("ordered_steps") or [],
                    "current_requirement": action_intent.get("current_requirement") or "",
                    "completed_subtasks": action_intent.get("completed_subtasks") or [],
                })

                fingerprint_payload = {
                    "url": current_url,
                    "action": action_intent.get("action"),
                    "target": action_intent.get("target") or {},
                    "current_requirement": action_intent.get("current_requirement") or "",
                    "state_fingerprint": hashlib.sha256(
                        json.dumps(browser_state, sort_keys=True, default=str).encode("utf-8")
                    ).hexdigest(),
                }
                fingerprint = hashlib.sha256(
                    json.dumps(fingerprint_payload, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
                attempt_number = execution_attempts.get(fingerprint, 0) + 1
                execution_attempts[fingerprint] = attempt_number
                generation_intent = dict(action_intent)
                previous_failure_records = [
                    record
                    for record in step_history
                    if record.get("action") == action_intent.get("action")
                    and (
                        not action_intent.get("current_requirement")
                        or record.get("current_requirement") == action_intent.get("current_requirement")
                    )
                    and not record.get("success", True)
                ]
                retry_number = len(previous_failure_records) + 1
                if previous_failure_records:
                    previous_failure = previous_failure_records[-1]
                    generation_intent["recovery_context"] = previous_failure.get("error", "")
                    generation_intent["failed_code"] = previous_failure.get("code", "")
                    generation_intent["retry_number"] = retry_number

                # Never execute a model-invented form value. Values must come
                # from the task goal or an approved chat response.
                if action_intent.get("action") == "file_upload":
                    if not await self._resolve_file_upload(task_id, session, action_intent.get("target") or {}):
                        await self._finish_task_failure(task_id, goal, "Required file upload was not completed.", start_time, visited_urls, step)
                        return
                    step_history.append({
                        "step": step,
                        "action": "file_upload",
                        "intent": action_intent.get("intent"),
                        "target": action_intent.get("target", {}),
                        "success": True,
                        "error": None,
                        "note": "File uploaded after human selection and approval.",
                    })
                    await self._save_checkpoint(task_id, step, step_history, visited_urls, execution_attempts, current_url)
                    continue

                if action_intent.get("action") == "request_user_input":
                    # AI has determined a value is missing from the goal.
                    # Go DIRECTLY to human-in-the-loop — no static mapping, no LLM goal-parsing.
                    # The user's reply will be recorded in step_history and fed back to the AI
                    # on the next planning iteration so it can generate the correct fill/select/check.

                    # Resolve the primary field the AI pointed to (for display only).
                    live_by_ref = {
                        str(el.get("ref")): el
                        for el in browser_state.get("interactive_elements", [])
                        if el.get("ref")
                    }
                    live_by_index = {
                        str(el.get("index")): el
                        for el in browser_state.get("interactive_elements", [])
                        if el.get("index") is not None
                    }
                    request_target = action_intent.get("target") or {}
                    request_ref = request_target.get("ref")
                    request_field = live_by_ref.get(str(request_ref)) if request_ref else None
                    if not request_field and request_target.get("selector", "").startswith("index "):
                        request_field = live_by_index.get(request_target["selector"][6:].strip())

                    # Also collect AI-listed required_fields for context.
                    ai_required_fields = []
                    for field_spec in action_intent.get("required_fields") or []:
                        lf = live_by_ref.get(str(field_spec.get("ref")))
                        if not lf:
                            sel = str(field_spec.get("selector") or "")
                            if sel.startswith("index "):
                                lf = live_by_index.get(sel[6:].strip())
                        if lf:
                            ai_required_fields.append(lf)

                    request_field = request_field or (ai_required_fields[0] if ai_required_fields else None)

                    field_label = (
                        self._human_form_field_label(request_field)
                        if request_field
                        else ""
                    )

                    # Build a clear, human-facing prompt for the chat.
                    raw_intent = str(action_intent.get("intent") or "").strip()
                    generic_markers = {
                        "request_user_input", "request form values from the user",
                        "fill the form", "executing planned action."
                    }
                    if raw_intent and raw_intent.lower() not in generic_markers and not raw_intent.lower().startswith("request form values"):
                        chat_prompt = raw_intent
                    elif field_label and field_label.lower() not in {"form field", "text value", "field"}:
                        chat_prompt = f"Please provide {field_label}."
                    else:
                        req_text = str(action_intent.get("current_requirement") or "").strip()
                        if req_text and req_text.lower() not in generic_markers and not req_text.lower().startswith("request form values"):
                            chat_prompt = req_text
                        elif raw_intent:
                            chat_prompt = raw_intent
                        else:
                            chat_prompt = "Please provide the required information to continue."

                    requirement_text = chat_prompt

                    logger.info(
                        "[FORM] Requesting human input for task %s: field=%s prompt=%s",
                        task_id, field_label, chat_prompt,
                    )

                    # ── Human-in-the-loop: pause task and wait for user reply ──
                    await self._update_task_status(task_id, TaskStatus.WAITING_FOR_HUMAN)
                    intervention = await self._create_intervention(
                        task_id=task_id,
                        intervention_type=HumanInterventionType.FORM_INPUT_REQUIRED,
                        prompt=chat_prompt,
                        action_payload={
                            "fields": ai_required_fields or ([request_field] if request_field else []),
                            "active_field": request_field,
                            "requirement": requirement_text,
                        },
                    )
                    await self._broadcast(task_id, "FORM_INPUT_REQUIRED", {
                        "intervention_id": intervention.get("id"),
                        "created_at": intervention.get("created_at"),
                        "prompt": chat_prompt,
                        "fields": ai_required_fields or ([request_field] if request_field else []),
                        "active_field": request_field,
                        "requirement": requirement_text,
                    })

                    resolution = await human_controller.wait_for_resolution(task_id)
                    if resolution.get("status") != HumanInterventionStatus.APPROVED.value:
                        await self._finish_task_failure(
                            task_id, goal,
                            "Task blocked: user did not provide the required form information.",
                            start_time, visited_urls, step,
                        )
                        return

                    response_data = resolution.get("user_response") or {}
                    user_reply = str(response_data.get("text") or "").strip()
                    new_file_text = str(response_data.get("file_text") or "").strip()
                    new_file_name = str(response_data.get("file_name") or "").strip()

                    if not user_reply and not new_file_text:
                        await self._finish_task_failure(
                            task_id, goal,
                            "Task blocked: user reply was empty.",
                            start_time, visited_urls, step,
                        )
                        return

                    if not user_reply and new_file_text:
                        user_reply = f"Attached file: {new_file_name or 'file.txt'}"

                    # Update file_context in memory and database with user reply and any attached file
                    reply_entry = f"- {requirement_text}: \"{user_reply}\""
                    if new_file_text:
                        reply_entry += f"\n  [Attached File {new_file_name or 'attachment'}]:\n{new_file_text}"

                    file_header = f"### USER PROVIDED VALUE IN CHAT:\n{reply_entry}"
                    if file_context and file_context.strip():
                        file_context = f"{file_context.strip()}\n\n{file_header}"
                    else:
                        file_context = file_header
                    await self._update_task_file_context(task_id, file_context)
                    logger.info(
                        "[FORM] Successfully integrated user reply into task %s file_context: %s",
                        task_id, user_reply
                    )

                    await self._update_task_status(task_id, TaskStatus.RUNNING)

                    # ── Record user reply and file content in step_history ──
                    history_user_reply = user_reply
                    if new_file_text:
                        history_user_reply = f"{user_reply}\n[File Content of {new_file_name or 'attachment'}]:\n{new_file_text}".strip()

                    step_history.append({
                        "step": step,
                        "action": "request_user_input",
                        "intent": requirement_text,
                        "target": request_target,
                        "success": True,
                        "error": None,
                        "user_reply": history_user_reply,
                        "has_file": bool(new_file_text),
                        "file_name": new_file_name or None,
                        "note": f"User provided: {history_user_reply}",
                    })
                    await self._save_checkpoint(task_id, step, step_history, visited_urls, execution_attempts, current_url)
                    logger.info(
                        "[FORM] User reply recorded for task %s step %s: %s (has_file: %s)",
                        task_id, step, user_reply, bool(new_file_text),
                    )
                    # Loop continues: AI will see the user_reply and file_context on the next step to decide the fill action.
                    continue

                if fingerprint in executed_fingerprints:
                    logger.warning("Skipping duplicate action fingerprint at step %s", step)
                    step_history.append({
                        "step": step,
                        "action": action_intent.get("action"),
                        "intent": action_intent.get("intent"),
                        "target": action_intent.get("target", {}),
                        "success": False,
                        "error": "Duplicate action suppressed; choose a new target or action."
                    })
                    await self._broadcast(task_id, "DUPLICATE_ACTION_SUPPRESSED", {
                        "step": step,
                        "action": action_intent.get("action"),
                        "target": action_intent.get("target", {})
                    })
                    continue

                # ── 6. DYNAMIC AI CODE GENERATION, VALIDATION, EXECUTION & RAG LOOP ──
                MAX_CODE_ATTEMPTS = 3  # 1: Initial AI, 2: AI Retry, 3: AI Retry + RAG Help
                code_snippet = ""
                exec_result = {"success": False, "error": "Execution not completed"}
                last_exec_error = None
                last_failed_code = None

                for code_attempt in range(1, MAX_CODE_ATTEMPTS + 1):
                    use_rag = (code_attempt == MAX_CODE_ATTEMPTS)
                    if use_rag:
                        logger.info("Step %s attempt %s: Consulting Playwright Knowledge RAG for assistance.", step, code_attempt)
                        await self._broadcast(task_id, "RAG_REPAIR_TRIGGERED", {
                            "step": step,
                            "action": action_intent.get("action"),
                            "attempt": code_attempt,
                            "last_error": last_exec_error,
                        })

                    await self._broadcast(task_id, "GENERATING_CODE", {
                        "step": step,
                        "action": action_intent.get("action"),
                        "attempt": code_attempt,
                        "use_rag": use_rag,
                    })

                    # 6a. Generate & Validate Code (with validator feedback retry)
                    validated_code = None
                    last_val_error = None
                    curr_candidate = ""

                    for val_attempt in range(1, 3):
                        try:
                            curr_candidate = await self.code_generator.generate_code(
                                task_id=task_id,
                                action_intent=generation_intent,
                                browser_state=browser_state,
                                use_rag=(use_rag or (val_attempt == 2 and code_attempt > 1)),
                                validation_error=last_val_error,
                                execution_error=last_exec_error,
                                failed_code=last_failed_code or curr_candidate,
                            )
                        except Exception as gen_err:
                            logger.warning("Code generator raised error at step %s: %s", step, gen_err)
                            last_val_error = str(gen_err)
                            continue

                        # 7. Validate AST, Locators, and URL Policy
                        val_check = code_validator.validate_code(
                            task_id,
                            curr_candidate,
                            browser_state=browser_state,
                            action_intent=action_intent,
                        )

                        if val_check["is_valid"]:
                            validated_code = curr_candidate
                            break
                        else:
                            last_val_error = val_check["error"]
                            logger.warning(
                                "Code validation rejected snippet at step %s (val attempt %s): %s",
                                step, val_attempt, last_val_error
                            )
                            await self._broadcast(task_id, "VALIDATION_FAILED", {
                                "step": step,
                                "error": last_val_error,
                                "val_attempt": val_attempt,
                                "will_retry": val_attempt < 2,
                            })

                    if not validated_code:
                        logger.error("Failed to generate validated code for step %s attempt %s: %s", step, code_attempt, last_val_error)
                        code_snippet = curr_candidate
                        exec_result = {"success": False, "error": f"Validation failed: {last_val_error}"}
                        last_exec_error = last_val_error
                        last_failed_code = curr_candidate
                        continue

                    code_snippet = validated_code

                    # 8. Execute Validated Playwright Snippet
                    if not await self._wait_if_paused(task_id):
                        return
                    if not session or not session.page or session.page.is_closed():
                        logger.info("Browser session closed for task %s before executing code at step %s.", task_id, step)
                        await self._finish_task_failure(task_id, goal, "Browser session was closed.", start_time, visited_urls, step)
                        return

                    await self._update_task_status(task_id, TaskStatus.RUNNING)
                    await self._broadcast(task_id, "CODE_EXECUTING", {
                        "step": step,
                        "code": code_snippet,
                        "attempt": code_attempt,
                    })

                    exec_result = await executor.execute_code(session.page, code_snippet)

                    if exec_result.get("success"):
                        logger.info("Playwright code execution succeeded on attempt %s at step %s", code_attempt, step)
                        try:
                            immediate_frame = await session.capture_base64_frame()
                            if immediate_frame:
                                await self._broadcast(task_id, "BROWSER_FRAME", {"frame_data": immediate_frame}, persist=False)
                        except Exception:
                            pass
                        break
                    else:
                        last_exec_error = exec_result.get("error", "Execution failed")
                        last_failed_code = code_snippet
                        logger.warning(
                            "Playwright execution failed at step %s (attempt %s/%s): %s",
                            step, code_attempt, MAX_CODE_ATTEMPTS, last_exec_error
                        )
                        await self._broadcast(task_id, "ACTION_EXECUTION_RETRY", {
                            "step": step,
                            "attempt": code_attempt,
                            "error": last_exec_error,
                            "will_use_rag": (code_attempt + 1 == MAX_CODE_ATTEMPTS),
                        })

                # Playwright completing a click/fill is not proof that the requested
                # UI transition or form operation succeeded. Re-observe the page and
                # require a state change for mutating browser actions.
                # Capture transient success/error notifications before they auto-dismiss.
                if not session or not session.page or session.page.is_closed():
                    logger.info("Browser session closed for task %s before post-action observation at step %s.", task_id, step)
                    if task_id in self.active_tasks:
                        await self._finish_task_failure(task_id, goal, "Browser session was closed.", start_time, visited_urls, step)
                    return
                post_browser_state = await observer.observe(session.page)
                if post_browser_state.get("is_closed"):
                    logger.info("Browser session closed during post-action observation for task %s at step %s.", task_id, step)
                    if task_id in self.active_tasks:
                        await self._finish_task_failure(task_id, goal, "Browser session was closed.", start_time, visited_urls, step)
                    return
                self._require_semantic_observation(post_browser_state)
                post_action_screenshot_path = await session.capture_screenshot(f"step_{step}_after.png")
                post_frame_snap = None
                try:
                    post_frame_snap = await session.capture_base64_frame()
                except Exception:
                    pass

                await self._broadcast(task_id, "BROWSER_OBSERVED", {
                    "step": step,
                    "phase": "post_action",
                    "url": post_browser_state.get("url", ""),
                    "title": post_browser_state.get("title"),
                    "screenshot_path": post_action_screenshot_path,
                    "frame_data": post_frame_snap,
                    "interactive_count": len(post_browser_state.get("interactive_elements", []))
                })
                state_diff = diff_states(browser_state, post_browser_state)
                state_changed = state_diff["state_changed"]
                action = action_intent.get("action")
                requested_popup_id = (action_intent.get("target") or {}).get("popup_id")
                previous_popup_ids = {
                    popup.get("id") for popup in browser_state.get("popups", []) if popup.get("id")
                }
                current_popup_ids = {
                    popup.get("id") for popup in post_browser_state.get("popups", []) if popup.get("id")
                }
                popup_resolved = bool(requested_popup_id and requested_popup_id not in current_popup_ids)
                if not requested_popup_id and action == "handle_popup":
                    popup_resolved = bool(previous_popup_ids - current_popup_ids)
                action_success = exec_result["success"] and (
                    state_changed or action in {"extract", "finish", "go_back", "click", "check", "uncheck", "hover", "press", "scroll", "wait"}
                    or (action == "handle_popup" and popup_resolved)
                )
                if exec_result["success"] and action in {"fill", "fill_form", "select_option"}:
                    # If no state change was observed after a fill/select, mark as unconfirmed.
                    # The next DOM snapshot will reveal if the value stuck.
                    if not state_changed:
                        action_success = False
                        exec_result = {
                            **exec_result,
                            "success": False,
                            "error": "The requested form value was not confirmed in the live DOM after the action.",
                        }
                visible_error_text = str(post_browser_state.get("visible_text_summary") or "").casefold()
                error_indicators = ("invalid login", "invalid credentials", "validation error", "failed to", "could not", "unable to")
                if action in {"click", "press", "fill", "fill_form", "select_option"} and any(
                    indicator in visible_error_text for indicator in error_indicators
                ):
                    action_success = False
                    exec_result = {
                        **exec_result,
                        "success": False,
                        "error": "The page reported a validation or operation error after the action.",
                    }
                if exec_result["success"] and not action_success:
                    exec_result = {
                        **exec_result,
                        "success": False,
                        "error": "Action executed but the current DOM did not change; the requested operation was not confirmed.",
                    }
                # Record Task Event
                step_record = {
                    "step": step,
                    "action": action_intent.get("action"),
                    "intent": action_intent.get("intent"),
                    "target": action_intent.get("target", {}),
                    "thought": action_intent.get("thought", ""),
                    "code": code_snippet,
                    "success": action_success,
                    "execution_success": exec_result.get("success", False),
                    "state_changed": state_changed,
                    "changed_sections": state_diff["changed_sections"],
                    "state_fingerprint_before": state_diff["before_fingerprint"],
                    "state_fingerprint_after": state_diff["after_fingerprint"],
                    "error": exec_result.get("error"),
                    "extracted_data": (
                        action_intent.get("extracted_data")
                        if action_intent.get("action") == "extract"
                        and action_intent.get("extracted_data") is not None
                        else self._build_dom_evidence(browser_state, goal)
                        if action_intent.get("action") == "extract"
                        else None
                    ),
                    "subtask_result": action_intent.get("subtask_result"),
                    "completed_subtasks": action_intent.get("completed_subtasks") or [],
                    "ordered_steps": action_intent.get("ordered_steps") or [],
                }
                step_history.append(step_record)
                await self._save_checkpoint(task_id, step, step_history, visited_urls, execution_attempts, current_url)

                await self._record_db_event(
                    task_id,
                    step,
                    action_intent,
                    code_snippet,
                    exec_result,
                    post_action_screenshot_path,
                )

                # Multitasking Milestone: If this step completed a subtask, broadcast its intermediate result immediately
                subtask_res = action_intent.get("subtask_result")
                if subtask_res and isinstance(subtask_res, dict) and subtask_res.get("summary"):
                    subtask_title = subtask_res.get("title") or action_intent.get("current_requirement") or f"Subtask {len(action_intent.get('completed_subtasks') or [])} Completed"
                    logger.info("Task %s completed subtask: %s - %s", task_id, subtask_title, subtask_res.get("summary"))
                    await self._broadcast(task_id, "SUBTASK_COMPLETED", {
                        "step": step,
                        "title": subtask_title,
                        "status": subtask_res.get("status") or "COMPLETED",
                        "summary": subtask_res.get("summary", ""),
                        "data": subtask_res.get("data") or {},
                        "completed_subtasks": action_intent.get("completed_subtasks") or [],
                        "ordered_steps": action_intent.get("ordered_steps") or [],
                    })

                if not action_success:
                    await self._broadcast(task_id, "ACTION_FAILED", {"step": step, "error": exec_result["error"]})
                    # Trigger recovery engine
                    rec = await self.recovery_engine.determine_recovery_strategy(
                        action_intent, exec_result["error"], post_browser_state, attempt_number
                    )
                    if rec.get("strategy") == "RE_OBSERVE":
                        execution_attempts.pop(fingerprint, None)
                    if rec["strategy"] == "ESCALATE":
                        await self._finish_task_failure(task_id, goal, f"Execution failed: {exec_result['error']}", start_time, visited_urls, step)
                        return
                else:
                    executed_fingerprints.add(fingerprint)

                if action == "finish" and action_success:
                    finish_data = action_intent.get("extracted_data") or self._build_dom_evidence(post_browser_state, goal)
                    finish_data = self._enrich_extracted_images(finish_data, post_browser_state)
                    await self._finish_task_success(
                        task_id,
                        goal,
                        action_intent.get("intent") or "Goal completed successfully.",
                        finish_data,
                        start_time,
                        visited_urls,
                        step,
                        step_history=step_history,
                        current_url=session.page.url,
                    )
                    return

                # Post-action stabilization: wait for page load, network idle, and dynamic rendering
                try:
                    if session and hasattr(session, "page") and session.page and not session.page.is_closed():
                        await session.page.wait_for_load_state("domcontentloaded", timeout=12000)
                        await session.page.wait_for_load_state("networkidle", timeout=6000)
                except Exception:
                    pass

                # Allow full rendering for dynamic listings, prices, and redirects
                logger.info("Waiting for page stabilization and dynamic content rendering...")
                await asyncio.sleep(3.5)

            # Max steps exceeded
            await self._finish_task_failure(
                task_id,
                goal,
                "Execution stopped by the safety fallback after prolonged progress without verified completion.",
                start_time,
                visited_urls,
                safety_step_limit,
            )

        except asyncio.CancelledError:
            logger.info("Autonomous loop for task %s cancelled cleanly.", task_id)
            return
        except Exception as e:
            if "Target page, context or browser has been closed" in str(e) or "TargetClosedError" in type(e).__name__:
                logger.info("Browser session closed for task %s: %s", task_id, e)
                if task_id in self.active_tasks:
                    await self._finish_task_failure(task_id, goal, "Browser session was closed.", start_time, visited_urls, len(step_history))
            else:
                logger.error(f"Unhandled error in autonomous loop for task {task_id}: {e}", exc_info=True)
                await self._finish_task_failure(task_id, goal, f"Unhandled system error: {str(e)}", start_time, visited_urls, len(step_history))
        finally:
            try:
                if session and hasattr(session, "page") and session.page and not session.page.is_closed():
                    if session.seed_path:
                        await session.persist_storage_state(session.seed_path)
            except Exception as storage_error:
                logger.debug("Could not persist browser account state for task %s: %s", task_id, storage_error)

            # Check task final status from database
            task_status = None
            async with async_session_factory() as check_session:
                t = await check_session.get(TaskModel, task_id)
                if t:
                    task_status = t.status

            # If task was explicitly cancelled or page was closed/crashed, close the browser session
            if task_status == TaskStatus.CANCELLED.value or (session and hasattr(session, "page") and session.page and session.page.is_closed()):
                await session_manager.close_session(task_id)
            else:
                logger.info(
                    "Retaining active browser session for task %s (url: %s) to support immediate continuation.",
                    task_id,
                    session.page.url if session and hasattr(session, "page") and session.page and not session.page.is_closed() else "unknown",
                )

            self.active_tasks.pop(task_id, None)
            self.paused_tasks.discard(task_id)

    @staticmethod
    def _enrich_extracted_images(data: Any, browser_state: Dict[str, Any]) -> Any:
        if not isinstance(data, dict):
            return data
        items = data.get("items")
        if not isinstance(items, list) or not items:
            return data

        listing_cards = browser_state.get("listing_cards", []) if browser_state else []
        discovered_links = browser_state.get("discovered_links", []) if browser_state else []

        card_images = [c.get("image") for c in listing_cards if c.get("image")]
        link_images = [l.get("image") for l in discovered_links if l.get("image")]
        all_pool = card_images + [img for img in link_images if img not in card_images]

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            curr_img = item.get("image") or item.get("img") or item.get("thumbnail") or item.get("imageUrl") or item.get("photo")
            if curr_img and not str(curr_img).startswith("data:"):
                continue

            title = str(item.get("title") or item.get("name") or item.get("product") or item.get("product_name") or "").lower()
            matched_img = None
            if title:
                title_words = set([w for w in title.split() if len(w) > 3])
                for card in listing_cards:
                    c_title = str(card.get("title", "")).lower()
                    c_img = card.get("image")
                    if c_img and any(w in c_title for w in title_words):
                        matched_img = c_img
                        break

            if not matched_img and idx < len(card_images):
                matched_img = card_images[idx]
            elif not matched_img and idx < len(all_pool):
                matched_img = all_pool[idx]

            if matched_img:
                item["image"] = matched_img

        return data

    @staticmethod
    def _build_dom_evidence(browser_state: Dict[str, Any], goal: str = "") -> Dict[str, Any]:
        listing_cards = browser_state.get("listing_cards", [])
        if listing_cards:
            return {"summary": "Evidence extracted from visible DOM listings.", "items": listing_cards}

        # Some sites expose result links without matching the observer's
        # site-specific card selectors. Preserve those live DOM links as cards.
        links = browser_state.get("discovered_links", [])
        goal_words = {
            word.lower() for word in goal.split()
            if len(word) > 2 and word.lower() not in {
                "search", "find", "give", "show", "get", "and", "the", "for", "with", "from", "prices", "price"
            }
        }
        link_items = []
        for link in links:
            title = str(link.get("text", "")).strip()
            url = str(link.get("url", "")).strip()
            if not title or not url or url.startswith("#"):
                continue
            title_words = set(title.lower().split())
            if goal_words and not (goal_words & title_words or any(word in title.lower() for word in goal_words)):
                continue
            link_items.append({
                "title": title,
                "url": url,
                "ref": link.get("ref"),
                "details": title,
                "image": link.get("image") or None
            })
            if len(link_items) >= 30:
                break
        if link_items:
            return {"summary": "Evidence extracted from visible DOM result links.", "items": link_items}

        return {
            "summary": "Evidence extracted from visible DOM text.",
            "text": browser_state.get("visible_text_summary", "")[:1500]
        }

    async def _finish_task_success(
        self,
        task_id: str,
        goal: str,
        summary: str,
        data: Any,
        start_time: datetime,
        visited_urls: List[str],
        action_count: int,
        step_history: Optional[List[Dict[str, Any]]] = None,
        current_url: Optional[str] = None,
    ):
        if step_history is not None:
            await self._save_checkpoint(task_id, action_count, step_history, visited_urls, {}, current_url or "")
            if isinstance(data, dict):
                subtasks = [s["subtask_result"] for s in step_history if s.get("subtask_result")]
                if subtasks and "subtasks" not in data:
                    data["subtasks"] = subtasks
        report = result_reporter.generate_report(task_id, goal, True, summary, data, None, start_time, visited_urls, action_count)
        await self._save_db_result(task_id, report)
        await self._update_task_status(task_id, TaskStatus.COMPLETED)
        await self._broadcast(task_id, "TASK_COMPLETED", report)

    async def _finish_task_failure(self, task_id: str, goal: str, reason: str, start_time: datetime, visited_urls: List[str], action_count: int):
        report = result_reporter.generate_report(task_id, goal, False, "Task failed.", None, reason, start_time, visited_urls, action_count)
        await self._save_db_result(task_id, report)
        await self._update_task_status(task_id, TaskStatus.FAILED)
        await self._broadcast(task_id, "TASK_FAILED", report)

    async def _record_db_event(
        self,
        task_id: str,
        step: int,
        action_intent: Dict,
        code: str,
        exec_result: Dict,
        screenshot_path: Optional[str] = None,
    ):
        async with async_session_factory() as session:
            screenshot_data = None
            if screenshot_path:
                try:
                    screenshot_data = await asyncio.to_thread(Path(screenshot_path).read_bytes)
                except OSError:
                    logger.debug("Could not read screenshot artifact for task event: %s", screenshot_path)
            evt = TaskEventModel(
                task_id=task_id,
                step=step,
                event_type=action_intent.get("action", "action"),
                intent=self._database_safe(action_intent.get("intent")),
                action_payload=self._database_safe(action_intent),
                generated_code=self._database_safe(code),
                url=self._database_safe(exec_result.get("current_url")),
                screenshot_path=self._database_safe(screenshot_path),
                screenshot_data=screenshot_data,
                success=exec_result["success"],
                error=self._database_safe(exec_result.get("error"))
            )
            session.add(evt)
            await session.commit()

    async def _save_checkpoint(
        self,
        task_id: str,
        step: int,
        step_history: List[Dict[str, Any]],
        visited_urls: List[str],
        execution_attempts: Dict[str, int],
        current_url: str,
    ):
        async with async_session_factory() as session:
            task = await session.get(TaskModel, task_id)
            if not task:
                return
            task.step_count = step
            task.current_url = current_url
            task.checkpoint = {
                "step": step,
                "step_history": step_history,
                "visited_urls": visited_urls,
                "execution_attempts": execution_attempts,
            }
            await session.commit()

    async def _save_db_result(self, task_id: str, report: Dict[str, Any]):
        async with async_session_factory() as session:
            res = TaskResultModel(
                task_id=task_id,
                success=report["success"],
                summary=self._database_safe(report["summary"]),
                data=self._database_safe(report["extracted_data"]),
                reason=self._database_safe(report["failure_reason"]),
                execution_time_seconds=report["execution_time_seconds"],
                pages_visited=self._database_safe(report["pages_visited"])
            )
            session.add(res)
            await session.commit()


task_manager = TaskManager()
