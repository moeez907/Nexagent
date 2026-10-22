"""
Recovery Engine & Loop Detector.
Handles action execution failures, repeated state loops, and alternative strategy escalation.
"""
import logging
from typing import Dict, Any, List, Optional

from app.llm.base import LLMProvider
from app.llm.prompts import RECOVERY_SYSTEM_PROMPT
from app.core.config import settings

logger = logging.getLogger("web_agent.agent.recovery")


class RecoveryEngine:
    """
    Manages failure recovery and prevents infinite action loops.
    """

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider

    def detect_loop(
        self,
        action_history: List[Dict[str, Any]],
        visited_urls: List[str]
    ) -> bool:
        """
        Detect whether the agent is stuck in an infinite repetition loop.
        """
        if len(action_history) < settings.MAX_SAME_STATE_REPETITIONS:
            return False

        recent = action_history[-settings.MAX_SAME_STATE_REPETITIONS:]
        recent_actions = [a.get("action") for a in recent]
        # Check if identical action fired 3 times in a row
        if len(set(recent_actions)) == 1 and recent_actions[0] not in ["extract", "finish"]:
            logger.warning(f"Loop Detector: Repeated identical action '{recent_actions[0]}' detected.")
            return True

        fingerprints = [a.get("state_fingerprint_after") for a in recent]
        if len(fingerprints) == len(recent) and fingerprints[0] and len(set(fingerprints)) == 1:
            logger.warning("Loop Detector: Repeated identical observed state detected.")
            return True

        action_targets = [
            (a.get("action"), str(a.get("target") or {}), a.get("state_fingerprint_before"))
            for a in action_history[-4:]
        ]
        if len(action_targets) == 4 and action_targets[0] == action_targets[2] and action_targets[1] == action_targets[3]:
            logger.warning("Loop Detector: A-B-A-B action loop detected.")
            return True

        # Check URL ping-pong loop (e.g. URL_A -> URL_B -> URL_A -> URL_B)
        if len(visited_urls) >= 4:
            if visited_urls[-1] == visited_urls[-3] and visited_urls[-2] == visited_urls[-4]:
                logger.warning("Loop Detector: Ping-pong URL navigation loop detected.")
                return True

        return False

    async def determine_recovery_strategy(
        self,
        failed_action: Dict[str, Any],
        error_message: str,
        browser_state: Dict[str, Any],
        attempt_count: int
    ) -> Dict[str, Any]:
        """
        Order of Recovery:
        1. Retry with refreshed locator/wait state if attempt < MAX_ACTION_RETRIES
        2. Re-observe / Refresh browser state
        3. Alternative interaction / navigation path
        4. Escalate to human or Abort
        """
        logger.info(f"Recovery Engine triggered for attempt {attempt_count}. Error: {error_message}")

        if attempt_count < settings.MAX_ACTION_RETRIES:
            interception_error = any(phrase in error_message.lower() for phrase in (
                "intercepts pointer events",
                "another element would receive the click",
                "element is obscured",
            ))
            if interception_error:
                return {
                    "strategy": "RE_OBSERVE",
                    "reason": "A dynamic overlay intercepted the action. Refreshing browser state before replanning.",
                    "next_suggested_intent": "Re-observe active popups and choose a currently actionable control.",
                }
            if "timeout" in error_message.lower() or "not found" in error_message.lower():
                return {
                    "strategy": "RE_OBSERVE",
                    "reason": "Element wait timeout. Refreshing browser state and locator bounds.",
                    "next_suggested_intent": "Re-observe page after load stabilization."
                }
            return {
                "strategy": "RETRY",
                "reason": "Transient error. Retrying action intent.",
                "next_suggested_intent": failed_action.get("intent", "Retry previous action")
            }

        # If LLM available, ask for dynamic recovery advice
        if self.llm_provider:
            user_prompt = f"""
FAILED ACTION:
{failed_action}

ERROR MESSAGE:
{error_message}

BROWSER STATE:
URL: {browser_state.get('url')}
Title: {browser_state.get('title')}

ATTEMPT COUNT: {attempt_count}
Recommend recovery strategy: RETRY, RE_OBSERVE, ALT_ACTION, or ESCALATE.
"""
            try:
                return await self.llm_provider.generate_structured(
                    system_prompt=RECOVERY_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    temperature=0.0
                )
            except Exception as e:
                logger.error(f"Recovery Engine LLM error: {e}")

        # Fallback strategy: Alternative navigation path or go_back
        return {
            "strategy": "ALT_ACTION",
            "reason": "Max retries exceeded for current target. Trying alternative link or go_back.",
            "next_suggested_intent": "Navigate to alternative search result or go back."
        }


recovery_engine = RecoveryEngine()
