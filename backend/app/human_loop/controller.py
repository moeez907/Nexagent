"""
Human-in-the-Loop Controller.
Handles state pauses, sensitive action confirmation, resume triggers, and timeouts.
"""
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.state_machine import HumanInterventionType, HumanInterventionStatus

logger = logging.getLogger("web_agent.human_loop.controller")


class HumanInterventionController:
    """
    Manages active human intervention requests and session pause/resume.
    """

    def __init__(self):
        # Maps task_id -> active intervention dictionary
        self._active_interventions: Dict[str, Dict[str, Any]] = {}
        # Event objects to unblock waiting execution tasks
        self._resume_events: Dict[str, asyncio.Event] = {}

    def create_intervention_request(
        self,
        task_id: str,
        intervention_type: HumanInterventionType,
        prompt: str,
        action_payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        intervention_id = str(uuid.uuid4())
        record = {
            "id": intervention_id,
            "task_id": task_id,
            "intervention_type": intervention_type.value,
            "status": HumanInterventionStatus.PENDING.value,
            "prompt": prompt,
            "action_payload": action_payload,
            "created_at": datetime.utcnow().isoformat(),
            "user_response": None
        }

        self._active_interventions[task_id] = record
        self._resume_events[task_id] = asyncio.Event()
        logger.info(f"Created Human Intervention request {intervention_id} for task {task_id} ({intervention_type.value}).")
        return record

    async def wait_for_resolution(self, task_id: str, timeout_seconds: float = 300.0) -> Dict[str, Any]:
        """
        Block task execution until human user responds via UI or timeout occurs.
        """
        event = self._resume_events.get(task_id)
        if not event:
            return {"status": HumanInterventionStatus.CANCELLED.value}

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
            record = self._active_interventions.get(task_id, {})
            return record
        except asyncio.TimeoutError:
            logger.warning(f"Human Intervention for task {task_id} timed out after {timeout_seconds}s.")
            if task_id in self._active_interventions:
                self._active_interventions[task_id]["status"] = HumanInterventionStatus.TIMEOUT.value
            return {"status": HumanInterventionStatus.TIMEOUT.value, "error": "Human intervention timed out."}
        finally:
            self._resume_events.pop(task_id, None)

    def resolve_intervention(
        self,
        task_id: str,
        approved: bool,
        response_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Invoked by API route when user submits response via React frontend.
        """
        record = self._active_interventions.get(task_id)
        if not record or record["status"] != HumanInterventionStatus.PENDING.value:
            return False

        record["status"] = HumanInterventionStatus.APPROVED.value if approved else HumanInterventionStatus.CANCELLED.value
        record["user_response"] = response_data or {}
        record["resolved_at"] = datetime.utcnow().isoformat()

        event = self._resume_events.get(task_id)
        if event:
            event.set()

        logger.info(f"Resolved Human Intervention for task {task_id} (Approved: {approved}).")
        return True

    def get_pending_intervention(self, task_id: str) -> Optional[Dict[str, Any]]:
        record = self._active_interventions.get(task_id)
        if record and record["status"] == HumanInterventionStatus.PENDING.value:
            return record
        return None


human_controller = HumanInterventionController()
