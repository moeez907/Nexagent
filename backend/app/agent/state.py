"""State comparison and goal-progress guards for browser actions."""
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List


_STATE_SECTIONS = ("url", "title", "visible_text_summary", "interactive_elements", "popups", "discovered_links")


def _normalized_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return {section: state.get(section) for section in _STATE_SECTIONS if section in state}


def fingerprint(state: Dict[str, Any]) -> str:
    payload = json.dumps(_normalized_state(state), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def diff_states(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    section_names = {
        "interactive_elements": "interactive",
        "visible_text_summary": "visible_text",
        "discovered_links": "links",
    }
    changed_sections = [
        section_names.get(section, section)
        for section in _STATE_SECTIONS
        if section in before or section in after
        if before.get(section) != after.get(section)
    ]
    return {
        "state_changed": bool(changed_sections),
        "changed_sections": changed_sections,
        "before_fingerprint": fingerprint(before),
        "after_fingerprint": fingerprint(after),
    }


def _words(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _action_text(record: Dict[str, Any]) -> str:
    target = record.get("target") or {}
    return " ".join(str(record.get(key) or "") for key in ("action", "intent", "thought", "current_requirement")) + " " + " ".join(
        str(target.get(key) or "") for key in ("text", "label", "value", "url")
    )


def _requirements(goal: str) -> List[str]:
    normalized = goal.casefold()
    requirements = []
    if re.search(r"\b(sign\s*in|log\s*in|login|authenticate)\b", normalized):
        requirements.append("authenticate")
    if re.search(r"\b(save|submit|send|place order|purchase|buy)\b", normalized):
        requirements.append("submit")
    return requirements


def evaluate_action_progress(goal: str, record: Dict[str, Any]) -> bool:
    if not record.get("execution_success", record.get("success", False)):
        return False
    if not record.get("state_changed", False) and record.get("action") not in {"extract", "finish"}:
        return False

    text = _action_text(record).casefold()
    if re.search(r"\b(open|show|view|go to)\b.*\b(login|sign\s*in|account)\b", text) and not re.search(
        r"\b(authenticated|signed\s*in|logged\s*in|successfully)\b", text
    ):
        return False
    return any(token in text for token in ("authenticate", "authenticated", "sign in", "logged in", "login", "save", "submit", "send", "purchase", "buy", "add to cart", "search", "select"))


def goal_completion_gate(
    goal: str,
    history: Iterable[Dict[str, Any]],
    verification: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    completed = set()
    for record in history:
        if not evaluate_action_progress(goal, record):
            continue
        text = _action_text(record).casefold()
        if re.search(r"\b(authenticated|signed\s*in|logged\s*in)\b", text):
            completed.add("authenticate")
        if re.search(r"\b(save|submit|send|place order|purchase|buy)\b", text):
            completed.add("submit")

    remaining = [requirement for requirement in _requirements(goal) if requirement not in completed]
    return {
        "goal_complete": bool((verification or {}).get("is_complete", False)) and not remaining,
        "remaining_requirements": remaining,
    }