"""
CAPTCHA Detection Sentinel.
Inspects browser state for real blocking CAPTCHA challenges, Cloudflare challenges, Google sorry pages, and eBay splash challenges.
Avoids false-positive triggers on normal pages with background reCAPTCHA badges or footer text.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger("web_agent.captcha.sentinel")


class CaptchaDetectionSentinel:
    """
    Detects real, blocking CAPTCHA challenges in observed browser state.
    """

    def inspect_state(self, browser_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inspect observed browser state for genuine blocking CAPTCHA markers.
        """
        is_detected = browser_state.get("captcha_detected", False)
        visible_text = browser_state.get("visible_text_summary", "").lower()
        title = browser_state.get("title", "").lower()
        url = browser_state.get("url", "").lower()

        # 1. Definite Challenge URLs
        if any(marker in url for marker in [
            "google.com/sorry",
            "challenges.cloudflare.com",
            "ebay.com/splashui/challenge",
            "daraz.pk/punish",
            "passport.daraz",
            "alibaba.com/punish",
            "aliexpress.com/punish",
            "/punish?"
        ]):
            is_detected = True

        # 2. Definite Blocking Challenge Titles
        if any(marker in title for marker in [
            "just a moment...",
            "attention required! | cloudflare",
            "pardon our interruption",
            "security verification",
            "punish"
        ]):
            is_detected = True

        # 3. Explicit Challenge Text Heuristics (strict blocking phrases)
        blocking_phrases = [
            "verify you are human",
            "verify that you are a human",
            "select all images with",
            "press & hold to confirm you are human",
            "unusual traffic from your computer network",
            "unusual traffic",
            "unusual activity",
            "drag the slider to verify",
            "slide to verify",
            "drag the slider",
            "drag to verify",
            "security verification",
            "complete the security check to access",
            "please solve this captcha",
            "confirm you are not a robot",
            "checking your browser before you access"
        ]

        text_match = any(phrase in visible_text for phrase in blocking_phrases)

        if is_detected or text_match:
            logger.warning(f"CAPTCHA Sentinel: Genuine challenge detected on active page! (URL: {url}, Title: {title})")
            return {
                "detected": True,
                "type": "captcha_challenge",
                "confidence": 0.95 if is_detected else 0.85,
                "message": "A security verification or bot challenge is blocking page access."
            }

        return {"detected": False, "type": None, "confidence": 0.0, "message": None}


captcha_sentinel = CaptchaDetectionSentinel()
