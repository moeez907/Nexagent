"""
Playwright Code Generator with Automation Templates, Prompt Augmentation, and AST Validation.
Converts structured action intent into minimal executable Python code snippet.
"""
import ast
import json
import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app.llm.base import LLMProvider
from app.llm.prompts import CODE_GENERATOR_SYSTEM_PROMPT
from app.rag.playwright_rag import rag_service
from app.agent.templates import template_registry

logger = logging.getLogger("web_agent.agent.code_generator")


class CodeGenerationResult(BaseModel):
    code: str = Field(description="Executable Python Playwright code string defining async def execute(page): ...")


class PlaywrightCodeGenerator:
    """
    Generates minimal single-operation Playwright script for structured action intent.
    Utilizes reusable automation templates, RAG prompt augmentation, and Python AST validation.
    """

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider

    def sanitize_code(self, code: str) -> str:
        """
        Sanitizes common Playwright method call syntax issues in LLM generated code.
        E.g. fixes `.all` without parentheses -> `.all()`.
        """
        if not code:
            return code
        import re
        code = re.sub(r'\.all(?!\w|\()', '.all()', code)
        code = re.sub(r'\.all_inner_texts(?!\w|\()', '.all_inner_texts()', code)
        code = re.sub(r'\.all_text_contents(?!\w|\()', '.all_text_contents()', code)
        code = re.sub(r'\.count(?!\w|\()', '.count()', code)
        return code

    def validate_code_syntax(self, code: str) -> bool:
        """
        Validates Python syntax using Abstract Syntax Tree (AST) parsing.
        Ensures `async def execute(page):` signature is present.
        """
        if not code or "async def execute(page)" not in code:
            return False
        try:
            ast.parse(code)
            return True
        except SyntaxError as e:
            logger.warning(f"Generated Playwright code failed AST syntax check: {e}")
            return False

    def generate_template_action(self, action_dict: Dict[str, Any]) -> Optional[str]:
        """
        Fast-path deterministic code generator via reusable automation templates.
        """
        return template_registry.generate_code(action_dict)

    async def generate_code(
        self,
        task_id: str,
        action_intent: Dict[str, Any],
        browser_state: Dict[str, Any],
        use_rag: bool = False,
        validation_error: Optional[str] = None,
        execution_error: Optional[str] = None,
        failed_code: Optional[str] = None,
    ) -> str:
        action = action_intent.get("action", "")

        # Pure state transitions without browser interaction
        if action in {"extract", "finish"}:
            return "async def execute(page):\n    pass"

        if action == "go_back":
            return "async def execute(page):\n    await page.go_back()"

        # Verify target refs are in the live DOM
        target = action_intent.get("target") or {}
        live_elements = browser_state.get("interactive_elements", [])
        live_refs = {str(item.get("ref")) for item in live_elements if item.get("ref")}

        if action in {"click", "fill", "fill_form", "select_option", "check", "uncheck", "handle_popup", "search"}:
            if target.get("fields"):
                fields = target.get("fields") or []
                for field_item in fields:
                    f_ref = str(field_item.get("ref") or "").strip()
                    if not f_ref or f_ref not in live_refs:
                        raise RuntimeError(
                            f"Target field ref '{f_ref}' is not present in the current DOM; replanning required."
                        )
            elif target.get("ref"):
                ref = str(target.get("ref") or "").strip()
                if ref not in live_refs:
                    raise RuntimeError(
                        f"{action.capitalize()} target ref '{ref}' is not present in the current DOM; replanning required."
                    )

        # 1. Extract live DOM details of targeted element(s) for the AI prompt
        target_ref = str(target.get("ref") or "")
        target_details = []
        if target_ref:
            for el in live_elements:
                if str(el.get("ref")) == target_ref:
                    target_details.append({
                        "ref": el.get("ref"),
                        "tag": el.get("tag"),
                        "type": el.get("type"),
                        "role": el.get("role"),
                        "text": el.get("text"),
                        "value": el.get("value"),
                        "placeholder": el.get("placeholder"),
                        "aria_label": el.get("aria_label"),
                        "label": el.get("label"),
                        "name": el.get("name"),
                        "options": el.get("options"),
                    })
                    break
        elif target.get("fields"):
            field_refs = {str(f.get("ref")) for f in target.get("fields") if f.get("ref")}
            for el in live_elements:
                if str(el.get("ref")) in field_refs:
                    target_details.append({
                        "ref": el.get("ref"),
                        "tag": el.get("tag"),
                        "type": el.get("type"),
                        "role": el.get("role"),
                        "text": el.get("text"),
                        "value": el.get("value"),
                        "placeholder": el.get("placeholder"),
                        "aria_label": el.get("aria_label"),
                        "label": el.get("label"),
                        "name": el.get("name"),
                        "options": el.get("options"),
                    })

        # 2. Build Feedback sections (Validation / Execution / Recovery)
        feedback_sections = []
        if validation_error:
            feedback_sections.append(
                f"<validation_feedback>\n"
                f"The previous generated code was rejected by the AST Code Validator:\n"
                f"<error>{validation_error}</error>\n"
                f"<failed_code>\n{failed_code or ''}\n</failed_code>\n"
                f"FIX INSTRUCTION: Correct the syntax/locator issue. All element locators MUST use:\n"
                f"page.locator('[data-agent-ref=\"<REF>\"]').first\n"
                f"Do not use forbidden locator methods like get_by_role, get_by_text, or raw selectors.\n"
                f"</validation_feedback>"
            )

        if execution_error:
            feedback_sections.append(
                f"<execution_feedback>\n"
                f"The previous code failed during Playwright browser execution:\n"
                f"<error>{execution_error}</error>\n"
                f"<failed_code>\n{failed_code or ''}\n</failed_code>\n"
                f"FIX INSTRUCTION: Inspect the DOM elements and the runtime error. Correct the locator, action method, wait strategy, or use click(force=True) if covered.\n"
                f"</execution_feedback>"
            )

        recovery_context = action_intent.get("recovery_context", "")
        if recovery_context and not execution_error:
            feedback_sections.append(
                f"<recovery_context>\n"
                f"<failure_reason>{recovery_context}</failure_reason>\n"
                f"<failed_code>{failed_code or action_intent.get('failed_code', '')}</failed_code>\n"
                f"</recovery_context>"
            )

        feedback_text = "\n\n".join(feedback_sections)

        # 3. Construct base prompt with current DOM snapshot & target info
        dom_snapshot = browser_state.get("dom_snapshot", "")
        base_prompt = f"""<code_generation_task>
<action_intent>
{json.dumps(action_intent, indent=2)}
</action_intent>

<current_browser_state>
  <url>{browser_state.get('url', '')}</url>
  <title>{browser_state.get('title', '')}</title>
</current_browser_state>

<target_element_dom_details>
{json.dumps(target_details, indent=2) if target_details else 'None'}
</target_element_dom_details>

<dom_snapshot>
{dom_snapshot}
</dom_snapshot>
</code_generation_task>
{feedback_text}

Analyze the live DOM snapshot above and generate a Python function `async def execute(page):` that performs this action safely using `page.locator('[data-agent-ref="<REF>"]').first`."""

        # 4. RAG Prompt Augmentation if requested
        user_prompt = base_prompt
        if use_rag:
            rag_intent = dict(action_intent)
            if execution_error:
                rag_intent["recovery_context"] = execution_error
            if failed_code:
                rag_intent["failed_code"] = failed_code
            user_prompt = rag_service.augment_prompt(base_prompt, rag_intent)
            logger.info("Augmented Playwright code generation prompt with RAG knowledge for task %s", task_id)

        # 5. AI Dynamic Code Generation
        if self.llm_provider:
            try:
                result = await self.llm_provider.generate_structured(
                    system_prompt=CODE_GENERATOR_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_model=CodeGenerationResult,
                    temperature=0.0
                )
                raw_code = result.get("code", "")
                code = self.sanitize_code(raw_code)
                if self.validate_code_syntax(code):
                    logger.info("AI successfully generated Playwright code for action: %s", action)
                    return code
                else:
                    logger.warning("LLM generated code failed syntax check: %s", code)
            except Exception as e:
                logger.error("LLM Code Generation call failed: %s", e)

        # 6. Fallback only if LLM is unavailable or crashes
        logger.warning("Using fallback generator for action: %s", action)
        return self._fallback_code_generator(action_intent)

    def _fallback_code_generator(self, action_dict: Dict[str, Any]) -> str:
        template_code = template_registry.generate_code(action_dict)
        if template_code and self.validate_code_syntax(template_code):
            return template_code

        action = action_dict.get("action")
        target = action_dict.get("target") or {}
        text = target.get("text", "")

        if action == "search":
            query = (text or "").replace("'", "\\'")
            ref = str(target.get("ref") or "").replace('"', '&quot;')
            if not query or not ref:
                return self._fallback_code_generator_error("Search target must contain a live DOM ref and query text.")
            return (
                "async def execute(page):\n"
                f"    search_box = page.locator('[data-agent-ref=\"{ref}\"]').first\n"
                f"    await search_box.fill('{query}')\n"
                "    await search_box.press('Enter')"
            )
        elif action == "select_option":
            option_value = target.get("value")
            option_label = target.get("text", "")
            ref = str(target.get("ref") or "").replace('"', '&quot;')
            option_argument = "value" if option_value else "label"
            option_text = option_value if option_value else option_label
            safe_value = str(option_text).replace("'", "\\'")
            if ref and option_text:
                return (
                    "async def execute(page):\n"
                    f"    await page.locator('[data-agent-ref=\"{ref}\"]').first.select_option({option_argument}='{safe_value}')"
                )
            return self._fallback_code_generator_error("Select target must contain a live DOM ref and option.")

        elif action == "click":
            ref = str(target.get("ref") or "").replace('"', '&quot;')
            if ref:
                return (
                    "async def execute(page):\n"
                    f"    await page.locator('[data-agent-ref=\"{ref}\"]').first.click()"
                )
            return self._fallback_code_generator_error("Click target must contain a live DOM ref.")
        elif action == "handle_popup":
            popup_action = str(target.get("popup_action") or target.get("dialog_action") or "dismiss").lower()
            if target.get("native_dialog"):
                dialog_method = "accept" if popup_action in {"accept", "confirm", "ok"} else "dismiss"
                return (
                    "async def execute(page):\n"
                    f"    page.once('dialog', lambda dialog: dialog.{dialog_method}())"
                )
            ref = str(target.get("ref") or "").replace('"', '&quot;')
            if ref:
                return (
                    "async def execute(page):\n"
                    f"    await page.locator('[data-agent-ref=\"{ref}\"]').first.click()"
                )
            return self._fallback_code_generator_error("Popup target must contain a live DOM ref.")
        elif action in ["extract", "finish"]:
            return (
                "async def execute(page):\n"
                "    pass"
            )
        
        return (
            "async def execute(page):\n"
            "    pass"
        )

    @staticmethod
    def _fallback_code_generator_error(message: str) -> str:
        safe_message = message.replace("'", "\\'")
        return (
            "async def execute(page):\n"
            f"    raise RuntimeError('{safe_message}')"
        )


code_generator = PlaywrightCodeGenerator()
