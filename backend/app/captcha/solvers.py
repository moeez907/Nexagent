"""
Modular CAPTCHA Solvers interface & Human Fallback.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class CaptchaSolver(ABC):
    @abstractmethod
    async def solve(self, task_id: str, challenge_info: Dict[str, Any]) -> Dict[str, Any]:
        pass


class HumanCaptchaHandler(CaptchaSolver):
    """
    Escalates CAPTCHA resolution to human operator via frontend UI preview.
    """

    async def solve(self, task_id: str, challenge_info: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "solved": False,
            "escalated_to_human": True,
            "message": challenge_info.get("message", "Please solve the CAPTCHA in the live browser preview.")
        }
