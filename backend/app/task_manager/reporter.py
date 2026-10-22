"""
Result Reporter.
Generates structured completion or failure reports with full execution metrics.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("web_agent.task_manager.reporter")


class ResultReporter:
    """
    Formulates honest, evidence-based task outcome reports.
    """

    def generate_report(
        self,
        task_id: str,
        goal: str,
        success: bool,
        summary: str,
        data: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        start_time: Optional[datetime] = None,
        visited_urls: Optional[List[str]] = None,
        action_count: int = 0
    ) -> Dict[str, Any]:
        execution_time = (datetime.utcnow() - start_time).total_seconds() if start_time else 0.0

        report = {
            "task_id": task_id,
            "goal": goal,
            "success": success,
            "summary": summary,
            "extracted_data": data or {},
            "failure_reason": reason if not success else None,
            "execution_time_seconds": round(execution_time, 2),
            "pages_visited": visited_urls or [],
            "total_actions": action_count,
            "completed_at": datetime.utcnow().isoformat()
        }

        logger.info(f"Generated Result Report for task {task_id}: Success={success}")
        return report


result_reporter = ResultReporter()
