"""
Goal Verifier.
Evaluates whether user's natural language goal is satisfied by extracted page evidence,
active DOM product listings, or direct answers on the current page.
"""
import logging
import re
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app.llm.base import LLMProvider
from app.llm.prompts import GOAL_VERIFIER_SYSTEM_PROMPT

logger = logging.getLogger("web_agent.agent.goal_verifier")


class GoalVerificationResult(BaseModel):
    is_complete: bool = Field(description="True if goal is genuinely achieved, False otherwise")
    confidence: float = Field(default=0.9, description="Confidence level between 0.0 and 1.0")
    reason: str = Field(description="Explanation of why goal is satisfied or what remains")
    verified_requirements: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    final_data: Optional[Dict[str, Any]] = Field(default=None, description="Extracted structured answers / items")


class GoalVerifier:
    """
    Evaluates goal satisfaction based on evidence and live DOM content.
    Instantly marks task complete when results/listings/answers are genuinely achieved.
    """

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider

    @staticmethod
    def _is_action_workflow(user_goal: str) -> bool:
        goal_lower = user_goal.casefold()
        action_keywords = [
            "fill", "form", "submit", "apply", "register", "signup", "sign up",
            "login", "log in", "checkout", "buy", "purchase", "book", "send",
            "post", "create account", "order", "enroll"
        ]
        return any(re.search(rf"\b{kw}\b", goal_lower) for kw in action_keywords)

    @classmethod
    def _has_submission_confirmation(cls, url: str, visible_text: str, dom_snapshot: str) -> bool:
        combined = f"{url} {visible_text} {dom_snapshot}".casefold()
        confirmation_indicators = [
            "formresponse",
            "your response has been recorded",
            "submit another response",
            "thank you for submitting",
            "thank you for your submission",
            "thank you for your response",
            "response has been recorded",
            "has been successfully submitted",
            "successfully submitted",
            "application submitted",
            "order confirmed",
            "registration complete",
            "submission confirmed",
            "your request has been processed",
        ]
        return any(ind in combined for ind in confirmation_indicators)

    @classmethod
    def _has_required_evidence(
        cls,
        user_goal: str,
        visible_text: str,
        extracted_data: Optional[Dict[str, Any]],
        url: str = "",
        dom_snapshot: str = "",
    ) -> bool:
        evidence_text = f"{visible_text} {extracted_data or ''}".lower()
        if not evidence_text.strip() and not url:
            return False

        if cls._is_action_workflow(user_goal):
            if not cls._has_submission_confirmation(url, visible_text, dom_snapshot):
                return False

        if re.search(r"\b(price|prices|cost|costs|how much)\b", user_goal.casefold()):
            items = (extracted_data or {}).get("items", []) if isinstance(extracted_data, dict) else []
            item_has_price = any(
                isinstance(item, dict) and str(item.get("price") or item.get("cost") or "").strip()
                for item in items
            )
            has_currency = bool(re.search(r"(?:rs\.?|usd|eur|gbp|pkr|\$|\u20ac|\u00a3)\s*\d|\d\s*(?:rs\.?|usd|eur|gbp|pkr)", evidence_text))
            return item_has_price or has_currency

        return True

    async def verify_goal(
        self,
        user_goal: str,
        browser_state: Dict[str, Any],
        extracted_data: Optional[Dict[str, Any]] = None,
        step_count: int = 0
    ) -> Dict[str, Any]:
        
        visible_text = browser_state.get('visible_text_summary', '')
        dom_snapshot = browser_state.get('dom_snapshot', '')
        listing_cards = browser_state.get('listing_cards', [])
        page_url = browser_state.get('url', '')
        page_title = browser_state.get('title', '')
        
        is_destination = bool(page_url and page_url != "about:blank")

        # Action/transaction workflows (forms, applications, submissions) must NOT be prematurely
        # marked complete simply because input fields are filled. They require submission confirmation.
        if self._is_action_workflow(user_goal) and not self._has_submission_confirmation(page_url, visible_text, dom_snapshot):
            logger.debug("GoalVerifier: Action workflow in progress. Awaiting submission confirmation before completion.")
            return {
                "is_complete": False,
                "confidence": 0.0,
                "reason": "Form or action workflow has not yet been submitted or confirmed.",
                "verified_requirements": [],
                "missing_requirements": ["Submit form and confirm successful submission"],
                "final_data": None
            }

        # 1. Evaluate goal satisfaction with LLM
        if self.llm_provider and (extracted_data or (is_destination and (listing_cards or visible_text.strip()))):
            user_prompt = f"""<verification_context>
<user_goal>
{user_goal}
</user_goal>

<page_url>{page_url}</page_url>
<page_title>{page_title}</page_title>

<visible_page_content>
{visible_text[:2000]}
</visible_page_content>

<dom_snapshot_summary>
{dom_snapshot[:2000]}
</dom_snapshot_summary>

<extracted_data>
{extracted_data or 'None'}
</extracted_data>
</verification_context>

Evaluate semantically whether the visible page content, product listings, or extracted evidence genuinely satisfies the <user_goal>.
Do not require exact words from the goal to appear in the DOM. Match entities,
values, roles, labels, state changes, and the requested workflow by meaning.
Intermediate pages or partial steps are not completion.
If YES:
1. Set "is_complete": true
2. Extract the exact answer/items into "final_data"
3. Provide a clear summary in "reason".

If NO:
Set "is_complete": false."""

            try:
                result = await self.llm_provider.generate_structured(
                    system_prompt=GOAL_VERIFIER_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_model=GoalVerificationResult,
                    temperature=0.0
                )
                if (
                    result.get("is_complete")
                    and not result.get("missing_requirements")
                    and result.get("verified_requirements")
                    and self._has_required_evidence(user_goal, visible_text, extracted_data, url=page_url, dom_snapshot=dom_snapshot)
                ):
                    logger.info(f"Goal verified satisfied at step {step_count}! Result: {result.get('reason')}")
                    return result
                if result.get("is_complete"):
                    logger.info("Verifier rejected completion because the live DOM does not contain all requested evidence.")
            except Exception as e:
                logger.error(f"Goal Verification LLM error: {e}")

        # 2. Accept only evidence produced from the current DOM observation.
        # Planner prose is intentionally not treated as proof of completion.
        has_dom_evidence = bool(
            extracted_data
            and isinstance(extracted_data, dict)
            and (extracted_data.get("items") or extracted_data.get("text"))
        )
        if (
            has_dom_evidence
            and self._has_required_evidence(user_goal, visible_text, extracted_data, url=page_url, dom_snapshot=dom_snapshot)
        ):
            return {
                "is_complete": True,
                "confidence": 0.9,
                "reason": "Goal satisfied with evidence from the current DOM observation.",
                "final_data": extracted_data
            }

        return {
            "is_complete": False,
            "confidence": 0.0,
            "reason": "Goal not yet fully satisfied.",
            "final_data": None
        }


goal_verifier = GoalVerifier()
