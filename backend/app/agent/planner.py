
import re
import logging
import json
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field

from app.llm.base import LLMProvider
from app.llm.prompts import PLANNER_SYSTEM_PROMPT
from app.agent.url_guard import url_guard

logger = logging.getLogger("web_agent.agent.planner")


class PlannerDecision(BaseModel):
    thought: str = Field(default="", description="Concise reasoning based on the current DOM and user goal")
    ordered_steps: List[str] = Field(default_factory=list, description="The user's complete goal decomposed into ordered requirements or subtasks")
    current_requirement: str = Field(default="", description="The first unfinished user requirement or subtask this action advances")
    completed_subtasks: List[str] = Field(default_factory=list, description="List of subtasks from ordered_steps that have already been fully accomplished")
    subtask_result: Optional[Dict[str, Any]] = Field(default=None, description="Intermediate result if a subtask was completed in this step: {'title': str, 'status': str, 'summary': str, 'data': Any}")
    target_evidence: str = Field(default="", description="Exact live DOM evidence showing why the target satisfies the current requirement")
    action: Literal["search", "click", "fill", "fill_form", "select_option", "check", "uncheck", "request_user_input", "file_upload", "handle_popup", "navigate", "extract", "go_back", "finish"] = Field(
        description="Action verb to execute. MUST be strictly one of: 'search', 'click', 'fill', 'fill_form', 'select_option', 'check', 'uncheck', 'request_user_input', 'handle_popup', 'navigate', 'extract', 'go_back', 'finish'"
    )
    intent: str = Field(default="", description="Short human-readable summary of the action")
    target: Dict[str, Any] = Field(default_factory=dict, description="Target details like selector ('index N'), url, text")
    required_fields: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Live DOM fields the AI identified as required to complete the current form requirement",
    )
    extracted_data: Optional[Dict[str, Any]] = Field(default=None, description="Extracted results when action is extract or finish")


class DecisionEngine:
    """
    Central reasoning controller for dynamic next-action determination.
    Fully generic and LLM-driven with schema-constrained JSON outputs.
    """

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider

    @staticmethod
    def _valid_semantic_dom(value: Any) -> bool:
        return (
            isinstance(value, str)
            and bool(value.strip())
            and value.lstrip().startswith("<semantic_dom>")
            and value.rstrip().endswith("</semantic_dom>")
            and bool(value.strip()[len("<semantic_dom>"):-len("</semantic_dom>")].strip())
        )

    @staticmethod
    def _goal_context(user_goal: str) -> Dict[str, Any]:
        urls = url_guard.extract_urls_from_text(user_goal)
        semantic_goal = re.sub(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+", " ", user_goal)
        semantic_goal = re.sub(
            r"^\s*(?:go\s+to|open|visit|navigate\s+to)\s+and\s+",
            "",
            semantic_goal,
            flags=re.IGNORECASE,
        )
        return {
            "urls": urls,
            "semantic_goal": re.sub(r"\s+", " ", semantic_goal).strip(" \t\r\n,;:-"),
        }

    @staticmethod
    def _validate_click_evidence(decision: Dict[str, Any], live_element: Dict[str, Any]) -> None:
        evidence = str(decision.get("target_evidence") or decision.get("intent") or "").casefold()
        if not evidence:
            return

        live_ref = str(live_element.get("ref") or "").casefold()
        live_index = str(live_element.get("index") or "").casefold()
        target = decision.get("target") or {}
        target_ref = str(target.get("ref") or "").casefold()
        target_selector = str(target.get("selector") or "").casefold()

        live_tokens = {
            token.casefold()
            for key in ("text", "label", "aria_label", "name")
            for token in re.findall(r"\w+", str(live_element.get(key) or ""))
            if len(token) > 1
        }
        evidence_clean = re.sub(r"\b(?:index\s*\d+|agent-\d+|button|link|element|input|click|the|labeled|at)\b", " ", evidence)
        evidence_tokens = {token.casefold() for token in re.findall(r"\w+", evidence_clean) if len(token) > 2}

        # If evidence explicitly describes a label (e.g. "labeled Cancel") but live element has a conflicting label (e.g. "Submit search")
        if live_tokens and evidence_tokens and not (live_tokens & evidence_tokens) and "labeled" in evidence:
            raise RuntimeError("LLM click evidence does not match the live element label; replanning required.")

        if (target_ref and target_ref == live_ref) or (live_index and (f"index {live_index}" in target_selector or target_selector == live_index)):
            return

        if (live_ref and live_ref in evidence) or (live_index and (f"index {live_index}" in evidence or live_index in evidence.split())):
            return

        if live_tokens & evidence_tokens:
            return

        raise RuntimeError("LLM click evidence does not identify the selected live element; replanning required.")

    @staticmethod
    def _validate_target_requirement(decision: Dict[str, Any], live_element: Dict[str, Any]) -> None:
        role = str(live_element.get("role") or "").casefold()
        tag = str(live_element.get("tag") or "").casefold()
        if role not in {"radio", "checkbox", "switch", "option", "combobox", "listbox"} and tag not in {"select"}:
            return
        requirement = str(decision.get("current_requirement") or "").casefold()
        context = " ".join(
            str(live_element.get(key) or "")
            for key in ("form_context", "label", "aria_label", "name")
        ).casefold()
        selection_tokens = set(re.findall(r"[a-z0-9]+", requirement)) & {
            "select", "choose", "pick", "option", "dropdown"
        }
        if not selection_tokens or not context:
            return
        requirement_tokens = set(re.findall(r"[a-z0-9]+", requirement))
        context_tokens = set(re.findall(r"[a-z0-9]+", context))
        if not requirement_tokens.intersection(context_tokens):
            raise RuntimeError(
                "LLM target belongs to a different form question than current_requirement; replanning required."
            )

    async def decide_next_action(
        self,
        task_id: str,
        user_goal: str,
        browser_state: Dict[str, Any],
        step_history: List[Dict[str, Any]],
        visited_urls: List[str],
        planning_error: Optional[str] = None,
        file_context: Optional[str] = None,
        loop_warning: Optional[str] = None,
        parent_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = browser_state.get("url", "")
        discovered_links = browser_state.get("discovered_links", [])
        semantic_dom_snapshot = browser_state.get('semantic_dom_snapshot')
        listing_cards = browser_state.get('listing_cards', [])
        page_title = browser_state.get('title', '')
        current_step = len(step_history) + 1
        goal_context = self._goal_context(user_goal)

        # Always register discovered links with URLPolicyGuard
        url_guard.register_discovered_links(task_id, discovered_links)

        # Handle initial start step when browser is at about:blank
        if not url or url == "about:blank":
            user_urls = url_guard.register_user_urls(task_id, user_goal)
            if user_urls:
                target = user_urls[0]
                logger.info(f"Goal contained user-provided URL: {target}")
                return {
                    "thought": "Initial step: Navigating directly to user-provided target URL.",
                    "action": "navigate",
                    "intent": f"Navigate to target URL: {target}",
                    "target": {
                        "url": target,
                        "url_source": "user"
                    }
                }

        # If LLM Provider is available, perform dynamic reasoning
        if self.llm_provider:
            if not self._valid_semantic_dom(semantic_dom_snapshot):
                raise RuntimeError("Semantic DOM is unavailable; planner invocation was blocked.")
            if step_history:
                history_lines = []
                # Keep up to the last 10 steps to prevent token bloat
                recent_steps = step_history[-10:] if len(step_history) > 10 else step_history
                if len(step_history) > 10:
                    history_lines.append(f"... [{len(step_history) - 10} earlier steps omitted for brevity] ...")
                for s in recent_steps:
                    step_num = s.get("step", 0)
                    action = s.get("action", "")
                    intent = s.get("intent", "")
                    success = s.get("success", True)
                    error = s.get("error")
                    status_str = "Success" if success else f"Failed ({error})"
                    target = s.get("target") or {}

                    if action == "request_user_input" and s.get("user_reply"):
                        # Render user reply prominently so AI can use it to fill all answering fields.
                        history_lines.append(
                            f"Step {step_num}: action=request_user_input | intent={intent} | "
                            f"outcome=Success\n"
                            f"  *** USER PROVIDED VALUE: \"{s['user_reply']}\" ***\n"
                            f"  → Check if this reply (or any previous replies/goal) contains values for MULTIPLE fields visible in the current DOM. If so, fill/select ALL matching fields together in a single fill_form action."
                        )
                    else:
                        history_lines.append(
                            f"Step {step_num}: action={action} | intent={intent} | "
                            f"target={target} | outcome={status_str}"
                        )
                history_text = "\n".join(history_lines)
            else:
                history_text = "No previous actions taken yet. This is Step 1 (Initial Step)."

            # Extract ALL user inputs across the ENTIRE history so past answers are NEVER lost due to step truncation
            all_user_inputs = []
            for s in step_history:
                if s.get("action") == "request_user_input" and s.get("user_reply"):
                    all_user_inputs.append({
                        "step": s.get("step"),
                        "question": s.get("intent") or "User Input",
                        "answer": s.get("user_reply"),
                    })

            user_inputs_block = ""
            if all_user_inputs:
                user_inputs_lines = [
                    "### PERMANENT RECORD OF ALL USER-PROVIDED ANSWERS (DO NOT RE-ASK FOR ANY OF THESE):"
                ]
                for item in all_user_inputs:
                    user_inputs_lines.append(
                        f"- Question/Intent: {item['question']}\n"
                        f"  User's Confirmed Answer: \"{item['answer']}\""
                    )
                user_inputs_block = "\n" + "\n".join(user_inputs_lines) + "\n"

            # Extract ALL completed subtasks and their intermediate results across the ENTIRE history
            all_completed_subtasks = []
            for s in step_history:
                if s.get("subtask_result") and isinstance(s["subtask_result"], dict):
                    all_completed_subtasks.append(s["subtask_result"])

            completed_subtasks_block = ""
            if all_completed_subtasks:
                subtask_lines = [
                    "### COMPLETED SUBTASKS & INTERMEDIATE RESULTS (ALREADY DONE — DO NOT REPEAT):"
                ]
                for item in all_completed_subtasks:
                    subtask_lines.append(
                        f"- [COMPLETED] {item.get('title', 'Subtask')}: {item.get('summary', '')}"
                    )
                    if item.get("data"):
                        subtask_lines.append(f"  Data: {json.dumps(item.get('data'))}")
                subtask_lines.append(
                    "→ Use the above findings to inform your next steps and focus ONLY on the NEXT unfinished subtask in ordered_steps."
                )
                completed_subtasks_block = "\n" + "\n".join(subtask_lines) + "\n"

            visited_text = ", ".join(visited_urls[-5:]) if visited_urls else "None"
            interactive_elements = browser_state.get("interactive_elements", [])
            popups = browser_state.get("popups", [])

            # Dynamically inspect live DOM form controls and their exact current state
            form_status_lines = []
            for el in interactive_elements:
                tag = str(el.get("tag") or "").lower()
                role = str(el.get("role") or "").lower()
                if tag in ("input", "textarea", "select") or role in ("checkbox", "radio", "combobox", "listbox", "textbox", "switch", "option"):
                    ref = el.get("ref")
                    idx = el.get("index")
                    label = el.get("label") or el.get("text") or el.get("name") or el.get("aria_label") or "Field"
                    val = str(el.get("value") or "").strip()
                    is_checked = el.get("selected_state") or el.get("checked") or el.get("aria_checked")
                    has_error = el.get("invalid") or el.get("validation_message")
                    req = " [REQUIRED]" if (el.get("required") or el.get("aria_required")) else ""

                    if is_checked:
                        state_str = "ALREADY CHECKED / SELECTED"
                    elif val and val != "[REDACTED]":
                        state_str = f"ALREADY FILLED (current_value='{val}')"
                    elif has_error:
                        state_str = f"VALIDATION ERROR ({el.get('validation_message') or 'Needs valid input'})"
                    else:
                        state_str = "EMPTY / UNFILLED"

                    form_status_lines.append(
                        f"- [{state_str}]{req} {label} (ref={ref}, index={idx}, role={role or tag})"
                    )

            live_form_summary = ""
            if form_status_lines:
                live_form_summary = (
                    "\n### LIVE DOM FORM FIELDS & CURRENT OBSERVED VALUES (STATUS):\n"
                    + "\n".join(form_status_lines)
                    + "\n"
                )

            def _compact_element(el: dict) -> dict:
                d = {
                    "index": el.get("index"),
                    "ref": el.get("ref"),
                    "tag": el.get("tag"),
                }
                for k in ("role", "label", "text", "name", "type", "value", "checked", "aria_checked", "selected_state", "form_context", "popup"):
                    v = el.get(k)
                    if v is not None and v != "" and v is not False:
                        d[k] = v
                href = el.get("compact_href") or el.get("href")
                if href:
                    d["href"] = href
                return d

            controls_text = "\n".join(
                str(_compact_element(element))
                for element in interactive_elements
            ) or "None"
            popups_text = json.dumps(popups, separators=(",", ":"), ensure_ascii=True) if popups else "None"
            raw_dom_size = len(browser_state.get("complete_dom_snapshot") or "")
            semantic_dom_size = len(semantic_dom_snapshot)
            reduction = ((raw_dom_size - semantic_dom_size) / raw_dom_size * 100) if raw_dom_size else 0
            logger.info(
                "Raw complete DOM size: %s chars; Semantic DOM size: %s chars; "
                "DOM reduction: %.2f%%; Planner DOM context size: %s chars",
                raw_dom_size,
                semantic_dom_size,
                reduction,
                semantic_dom_size,
            )

            stage_guidance = (
                "Treat the TASK GOAL as an ordered workflow, not as a general request. "
                "Also consider the current browser state, including the live DOM snapshot and take actions according to current dom."
                "Reconstruct every requested step from the goal and compare it with the "
                "complete action history. Choose exactly one next action for the first "
                "unfinished step. A successful earlier step is complete only when its "
                "outcome and the current DOM confirm it; never repeat it or skip ahead. "
                "Do not extract or finish because intermediate text, cards, or a page "
                "is visible. Extract/finish only after the final requested operation has "
                "succeeded and the current DOM contains its result. If the website blocks "
                "progress with CAPTCHA or a verification challenge, do not invent data or "
                "bypass it: stop and request human intervention. For ordinary OTP, consent, "
                "permission, upload, approval, login, checkout, or payment forms, ask the "
                "user for missing values and continue after DOM verification."
                "If an outcome failed, analyze the exact error, failed code/action, goal, history, "
                "and current DOM before selecting the next action. For a runtime failure, choose "
                "one alternative locator or action supported by the live DOM. For a validation or "
                "URL policy failure, never repeat the rejected code or URL. Never invent, guess, "
                "or synthesize a destination URL: use only an exact user-provided or browser-"
                "discovered URL. If the user gives a website name without an exact URL, search "
                "for that name through the allowed search-engine flow."
                "Select the exact DOM target whose semantic meaning fulfills the first unfinished user step."
                "A link or button is valid when it is relevant to that step; never choose a target only because it is nearby."
                "Always preserve the user's complete goal, including the requested result or data to extract."
                " When the user goal requires finding a specific product, item, article, or person on a website, "
                "always inspect the DOM for an on-site search feature (e.g. search input, placeholder containing 'search', "
                "or search button/icon link such as href='/search') and prioritize using search directly instead of guessing "
                "categories or paginating through unrelated collections. If a visited collection or page does NOT contain "
                "the requested item, NEVER oscillate back and forth between the same pages — switch strategy and use site search "
                "or main navigation instead."
                " If an active popup, modal, overlay, newsletter, promotion, discount offer (e.g. '10% off', phone/email signup), cookie banner, or dialog is blocking the page and is NOT part of the user's explicit goal, "
                "you MUST immediately choose its DOM close/cross/dismiss control (e.g. 'u-close-button', 'close', 'X', 'Not Now', 'No thanks', 'Dismiss', 'Cancel', 'Decline') to dismiss it and unblock page interaction. "
                "NEVER attempt to interact with background page elements behind an active blocking popup or overlay. "
                "If the popup is genuinely part of the user's requested workflow (e.g., checkout/login modal), interact with its controls or request required missing inputs."
                " If an active notification reports success after a mutating action, treat it as supporting evidence only. "
                "Verify the requested result from durable current DOM state such as an item, count, status, or destination "
                "change. If a dismissible notification remains and the next action needs a clear page, choose its exact "
                "close control from popup.close_refs/close_controls through handle_popup and verify that it disappears. If durable evidence is missing, report "
                "the action as unverified in the next decision and choose a DOM-supported retry or verification action."
                "\n\n=== FORM FILLING — AI OWNS ALL FORM DECISIONS ===\n"
                "You are fully responsible for analyzing every form field in the DOM and deciding "
                "whether a value is available or must be requested from the user. Do NOT rely on "
                "any external system to approve or block your form decisions.\n\n"
                "STEP-BY-STEP DYNAMIC FORM RESOLUTION (FROM LIVE DOM):\n"
                "1. LIVE DOM INSPECTION — EXAMINE 'LIVE DOM FORM FIELDS & CURRENT OBSERVED VALUES':\n"
                "   - If a field or control is marked [ALREADY FILLED] or [ALREADY CHECKED / SELECTED], IT IS ALREADY COMPLETED IN THE DOM!\n"
                "   - NEVER choose request_user_input for an already-filled or already-checked field!\n"
                "   - NEVER re-click an already [ALREADY CHECKED / SELECTED] checkbox or radio button (clicking it would uncheck/deselect it)!\n"
                "2. RESOLVE UNFILLED / EMPTY FIELDS:\n"
                "   - Find which fields are [EMPTY / UNFILLED] or have a [VALIDATION ERROR] in the live DOM.\n"
                "   - Check the COMPLETE USER GOAL, ATTACHED FILE CONTEXT, and PERMANENT RECORD OF ALL USER-PROVIDED ANSWERS.\n"
                "   - If the value is known from any of those sources (e.g. Country is 'Pakistan', Employment is 'Freelancer', Meeting Time is '8:00 PM', Technologies is 'HTML, CSS, JavaScript'):\n"
                "     FILL or SELECT it immediately in the DOM! Use 'fill_form' to batch-fill all matching fields at once.\n"
                "3. ASK ONLY FOR GENUINELY MISSING VALUES:\n"
                "   - If and ONLY if a required field is [EMPTY / UNFILLED] or has a [VALIDATION ERROR], AND its value was NEVER provided in the goal, file, or chat history: ask the user for that specific missing field via request_user_input.\n"
                "   - Ask for ONLY ONE specific missing field at a time.\n"
                "4. ADVANCE AND SUBMIT:\n"
                "   - Once all visible required fields on the current page are [ALREADY FILLED] or [ALREADY CHECKED / SELECTED], click 'Next' (for multi-page forms) or 'Submit'!\n"
                "   - Never choose action 'finish' until the form submission confirmation screen is visibly displayed.\n"
                "5. For passwords, OTPs, payment data, legal consent, signatures, and CAPTCHA: always "
                "   use request_user_input — never guess or invent these values.\n"
                "6. Never fill a field with an invented, guessed, or default value. "
                "   Every value must either come from the explicit user goal or from an approved user reply.\n"
            )

            file_context_section = f"\n### ATTACHED FILE CONTEXT (.TXT):\n{file_context.strip()}\n" if file_context and file_context.strip() else ""
            loop_warning_section = f"\n### CRITICAL LOOP WARNING:\n{loop_warning}\n" if loop_warning else ""

            mandatory_replan_rule = (
                f"The previous proposed action was rejected: '{planning_error}'. "
                f"You MUST analyze this rejection reason and the current live DOM snapshot to choose a different, valid action (e.g. if a blocking popup is active, dismiss or handle the popup first before targeting background elements; if a target or option was invalid, choose the correct matching element from the current DOM). Do not repeat the rejected target or action."
                if planning_error
                else "No target has been rejected yet."
            )

            continuation_section = ""
            if parent_context:
                prev_goals = parent_context.get("previous_goals", [])
                prev_results = parent_context.get("previous_results", [])
                lines = ["### CONVERSATION WORKFLOW HISTORY (Continuing on current live browser page):"]
                if prev_goals:
                    lines.append("Previous Completed Goals in this Workflow:")
                    for i, pg in enumerate(prev_goals, 1):
                        lines.append(f"  {i}. {pg}")
                if prev_results:
                    lines.append("\nResults & Summaries from Previous Goals:")
                    for pr in prev_results:
                        summary = pr.get("summary") or "Completed"
                        data_preview = ""
                        if pr.get("data"):
                            try:
                                d_json = json.dumps(pr.get("data"), ensure_ascii=False)
                                if len(d_json) > 500:
                                    d_json = d_json[:500] + "..."
                                data_preview = f" | Data: {d_json}"
                            except Exception:
                                pass
                        lines.append(f"  - Goal: \"{pr.get('goal')}\" -> Outcome: {summary}{data_preview}")
                lines.append(
                    "\nCRITICAL CONTINUATION INSTRUCTIONS:\n"
                    "1. You are continuing this workflow directly on the current live browser page. Do NOT restart or re-navigate to the home page or search engine unless the new goal explicitly specifies a different website.\n"
                    "2. Retain context: Use the current live DOM and the previous outcomes to execute the NEW user goal below directly from where you left off.\n"
                    "3. If the user goal asks to filter, inspect, click an item, extract details, or take the next step on the current page, interact directly with the matching elements in the current DOM."
                )
                continuation_section = "\n" + "\n".join(lines) + "\n"

            user_prompt = f"""### COMPLETE USER GOAL:
{user_goal}
{continuation_section}
{file_context_section}
{user_inputs_block}
{live_form_summary}
### SEMANTIC TASK:
{goal_context['semantic_goal'] or user_goal.strip()}

### USER-PROVIDED WEBSITE CONTEXT:
{', '.join(goal_context['urls']) if goal_context['urls'] else 'None'}

{completed_subtasks_block}
### MULTITASKING & EXECUTION GUIDANCE:
1. Decompose the goal into `ordered_steps` (Subtask 1, Subtask 2, ...).
2. Focus strictly on the active `current_requirement`.
3. When a subtask finishes, provide its outcome in `subtask_result`, append its name to `completed_subtasks`, and advance to the next unfinished subtask.
4. DO NOT choose 'finish' if there are remaining unfinished subtasks in `ordered_steps`!
5. For form fields, if the user has provided values (in goal or in ANY user reply in PREVIOUS STEPS) for multiple fields visible in the current DOM, choose action 'fill_form' to fill/select ALL matching fields at once.
6. For interactive actions, target ref and selector/index must identify the same live element.

### CURRENT BROWSER STATE:
URL: {url}
Page Title: {page_title}
Visited URLs: {visited_text}

### PREVIOUS STEPS (What you already executed):
{history_text}

### ACTIVE POPUPS, MODALS, AND NATIVE DIALOGS
{popups_text}

### PREVIOUS PLANNING ERROR:
{planning_error or 'None'}
{loop_warning_section}
### MANDATORY REPLAN RULE:
{mandatory_replan_rule}

### EXECUTION CONTRACT:
The previous steps are authoritative workflow state. Failed or duplicate-suppressed
steps are unfinished and must be reconsidered with the current DOM. A successful step
does not prove later steps are complete. Never report completion until the final user-
requested operation is verified in the current DOM.

### STAGE INSTRUCTION:
{stage_guidance}

### SEMANTIC COMPLETE DOM SNAPSHOT:
{semantic_dom_snapshot}

Respond with your JSON decision matching the required schema:"""

            # Print exact DOM & Prompt to Terminal for User
            try:
                print("\n" + "=" * 80, flush=True)
                print(f"[STEP {current_step}] SENDING PROMPT & STRUCTURED DOM TO LLM", flush=True)
                print("=" * 80, flush=True)
                print(f"USER GOAL: {user_goal}", flush=True)
                if file_context and file_context.strip():
                    print(f"ATTACHED FILE CONTEXT ({len(file_context)} chars):\n{file_context[:500]}...", flush=True)
                print(f"CURRENT URL: {url}", flush=True)
                print(f"PAGE TITLE: {page_title}", flush=True)
                print(f"HISTORY:\n{history_text}\n", flush=True)
                print(f"SEMANTIC DOM SNAPSHOT ({len(semantic_dom_snapshot)} chars):\n{semantic_dom_snapshot}\n", flush=True)
                print("=" * 80 + "\n", flush=True)
            except Exception:
                pass

            try:
                decision = await self.llm_provider.generate_structured(
                    system_prompt=PLANNER_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_model=PlannerDecision,
                    temperature=0.1
                )

                raw_thought = decision.get("thought", "")
                sanitized_thought = re.sub(r'(?i)\bthe user has not (?:yet )?performed\b', 'I have not yet performed', raw_thought)
                sanitized_thought = re.sub(r'(?i)\bthe user should\b', 'I should', sanitized_thought)
                sanitized_thought = re.sub(r'(?i)\bthe user will\b', 'I will', sanitized_thought)
                decision["thought"] = sanitized_thought

                # Multitasking guard: Prevent premature finish if unfinished subtasks remain
                if decision.get("action") == "finish":
                    ordered_steps = decision.get("ordered_steps") or []
                    reported_completed = decision.get("completed_subtasks") or []
                    all_known_completed = set(reported_completed) | {
                        c.get("title", "").strip() for c in all_completed_subtasks if c.get("title")
                    }
                    if len(ordered_steps) > 1:
                        unfinished = [
                            st for st in ordered_steps
                            if not any(
                                (c.lower() in st.lower() or st.lower() in c.lower())
                                for c in all_known_completed if c
                            )
                        ]
                        if len(unfinished) > 1:
                            raise RuntimeError(
                                f"Premature finish rejected: The user goal contains multiple subtasks. "
                                f"Completed: {list(all_known_completed)}. "
                                f"Unfinished subtasks remaining: {unfinished}. "
                                f"Please execute the next subtask ('{unfinished[0]}') and report its subtask_result before calling finish."
                            )

                if not decision.get("intent"):
                    decision["intent"] = decision.get("thought", "Executing planned action.")

                if "target" not in decision or not isinstance(decision.get("target"), dict):
                    decision["target"] = {}

                target = decision["target"]
                target_ref = target.get("ref")
                target_element = next(
                    (element for element in interactive_elements if target_ref and element.get("ref") == target_ref),
                    None,
                )
                upload_text = " ".join(
                    str((target or {}).get(key) or "")
                    for key in ("text", "label", "aria_label", "intent")
                ).casefold()
                upload_element_text = " ".join(
                    str((target_element or {}).get(key) or "")
                    for key in ("text", "label", "aria_label", "type")
                ).casefold()
                if decision.get("action") == "request_user_input" and (
                    target_element and target_element.get("upload_control")
                ):
                    decision["action"] = "file_upload"
                    decision["intent"] = decision.get("intent") or "Request the required file upload"
                if decision.get("action") == "file_upload":
                    upload_element = target_element
                    if not upload_element or not upload_element.get("upload_control"):
                        upload_element = next(
                            (
                                element for element in interactive_elements
                                if element.get("upload_control")
                            ),
                            None,
                        )
                    if upload_element:
                        target["ref"] = upload_element.get("ref")
                        target["selector"] = f"index {upload_element.get('index')}"
                        target["field_label"] = (
                            upload_element.get("label")
                            or upload_element.get("aria_label")
                            or upload_element.get("text")
                            or "file upload"
                        )
                    upload_content = (
                        f"{upload_text} {upload_element_text} "
                        f"{user_goal} {decision.get('current_requirement') or ''}"
                    ).casefold()
                    target["upload_mode"] = (
                        "folder"
                        if any(marker in upload_content for marker in ("folder", "directory", "multiple files", "entire folder"))
                        else "file"
                    )

                # Resolve only the exact target identity returned by the model.
                target_for_resolution = decision.get("target") or {}
                if decision.get("action") in {
                    "click", "fill", "fill_form", "select_option", "handle_popup",
                    "check", "uncheck", "search",
                } and (
                    decision.get("action") != "handle_popup"
                    or target_for_resolution.get("ref")
                    or target_for_resolution.get("fields")
                    or str(target_for_resolution.get("selector") or "").startswith("index ")
                ):
                    target = decision.setdefault("target", {})
                    interactive_elements = browser_state.get("interactive_elements", [])

                    if decision.get("action") == "fill_form" or target.get("fields"):
                        fields = target.get("fields") or []
                        resolved_fields = []
                        for field_item in fields:
                            f_ref = field_item.get("ref")
                            f_sel = str(field_item.get("selector") or "")
                            f_idx = f_sel.replace("index ", "", 1).strip() if f_sel.startswith("index ") else ""

                            ref_el = next(
                                (el for el in interactive_elements if f_ref and el.get("ref") == f_ref),
                                None,
                            )
                            idx_el = next(
                                (el for el in interactive_elements if f_idx and str(el.get("index")) == f_idx),
                                None,
                            )
                            if not f_ref and idx_el:
                                f_ref = idx_el.get("ref")
                                ref_el = idx_el
                            if not ref_el:
                                raise RuntimeError(
                                    f"LLM target field ref '{f_ref or f_sel}' was not found in the current DOM; replanning required."
                                )
                            resolved_field = dict(field_item)
                            resolved_field["ref"] = ref_el.get("ref")
                            resolved_field["selector"] = f"index {ref_el.get('index')}" if ref_el.get("index") is not None else f_sel
                            resolved_field["action"] = resolved_field.get("action") or ("select_option" if ref_el.get("tag") == "select" else "fill")
                            resolved_fields.append(resolved_field)

                        target["fields"] = resolved_fields
                        if resolved_fields:
                            target.setdefault("ref", resolved_fields[0]["ref"])
                            target.setdefault("selector", resolved_fields[0]["selector"])
                    else:
                        target_ref = target.get("ref")
                        target_selector = str(target.get("selector") or "")
                        target_index = target_selector.replace("index ", "", 1).strip() if target_selector.startswith("index ") else ""

                        if decision.get("action") == "search" and not target_ref and not target_index:
                            search_candidates = [
                                element for element in interactive_elements
                                if str(element.get("role") or "").casefold() in {"combobox", "searchbox", "textbox"}
                                or str(element.get("tag") or "").casefold() in {"textarea", "input"}
                                and (
                                    any(k in str(element.get("name") or "").casefold() for k in ("search", "q", "query", "keyword", "k"))
                                    or any(k in str(element.get("label") or "").casefold() for k in ("search", "find", "query"))
                                    or any(k in str(element.get("placeholder") or "").casefold() for k in ("search", "find", "query", "type"))
                                    or any(k in str(element.get("aria_label") or "").casefold() for k in ("search", "find", "query"))
                                    or str(element.get("type") or "").casefold() == "search"
                                )
                            ]
                            if not search_candidates:
                                search_candidates = [
                                    element for element in interactive_elements
                                    if str(element.get("tag") or "").casefold() in {"input", "textarea"}
                                    and str(element.get("type") or "text").casefold() in {"text", "search", ""}
                                    and not element.get("disabled") and not element.get("readonly")
                                ]
                            if search_candidates:
                                target_ref = search_candidates[0].get("ref")
                                target["ref"] = target_ref
                                target["selector"] = f"index {search_candidates[0].get('index')}"
                                target_index = str(search_candidates[0].get("index", ""))

                        ref_element = next(
                            (element for element in interactive_elements if target_ref and element.get("ref") == target_ref),
                            None,
                        )
                        index_element = next(
                            (
                                element for element in interactive_elements
                                if target_index and str(element.get("index")) == target_index
                            ),
                            None,
                        )
                        resolved_refs = {
                            element.get("ref")
                            for element in (ref_element, index_element)
                            if element and element.get("ref")
                        }
                        if len(resolved_refs) > 1:
                            raise RuntimeError(
                                "LLM target ref and selector identify different live elements; replanning required."
                            )
                        if not ref_element and index_element:
                            ref_element = index_element
                            target_ref = ref_element.get("ref")
                            target["ref"] = target_ref
                        elif ref_element:
                            target_ref = ref_element.get("ref")
                            target["ref"] = target_ref

                        if not ref_element:
                            raise RuntimeError(
                                "LLM target has no live ref or current DOM index; replanning required."
                            )

                        target.update({
                            "ref": ref_element.get("ref"),
                            "selector": f"index {ref_element.get('index')}" if ref_element.get('index') is not None else target.get("selector", ""),
                            "text": (
                                target.get("text") or ref_element.get("text") or ref_element.get("label") or ref_element.get("value") or ""
                                if decision.get("action") in {"search", "fill"}
                                else ref_element.get("text") or ref_element.get("label") or target.get("text", "")
                                if decision.get("action") == "click"
                                else target.get("text") or target.get("value", "")
                            ),
                            "url": ref_element.get("href") or target.get("url", ""),
                        })
                        if ref_element.get("popup") and ref_element["popup"].get("id"):
                            target["popup_id"] = ref_element["popup"]["id"]
                        if decision.get("action") == "click":
                            self._validate_click_evidence(decision, ref_element)

                # Print LLM Decision to Terminal for User
                try:
                    print("=" * 80, flush=True)
                    print(f"[STEP {current_step}] LLM DECISION:", flush=True)
                    print(f"   Thought : {decision.get('thought')}", flush=True)
                    print(f"   Action  : {decision.get('action')}", flush=True)
                    print(f"   Intent  : {decision.get('intent')}", flush=True)
                    print(f"   Requirement: {decision.get('current_requirement')}", flush=True)
                    print(f"   Target Evidence: {decision.get('target_evidence')}", flush=True)
                    print(f"   Target  : {decision.get('target')}", flush=True)
                    if decision.get("extracted_data"):
                        print(f"   Extracted Data: {decision.get('extracted_data')}", flush=True)
                    print("=" * 80 + "\n", flush=True)
                except Exception:
                    pass

                return decision

            except RuntimeError:
                raise
            except Exception as e:
                logger.error(f"Planner LLM reasoning error: {e}")
                raise RuntimeError("LLM planner failed; fallback planning is disabled.") from e

        raise RuntimeError("LLM provider is required for generic goal planning; fallback planning is disabled.")

