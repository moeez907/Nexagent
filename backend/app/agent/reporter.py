"""
Result Reporter Module.
Generates structured task completion and failure summary reports.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("web_agent.agent.reporter")


class ResultReporter:
    """
    Generates structured execution result summary for autonomous tasks.
    """

    def generate_report(
        self,
        task_id: str,
        goal: str,
        success: bool,
        summary: str,
        extracted_data: Optional[Any] = None,
        failure_reason: Optional[str] = None,
        start_time: Optional[datetime] = None,
        pages_visited: Optional[List[str]] = None,
        action_count: int = 0
    ) -> Dict[str, Any]:
        execution_time = 0.0
        if start_time:
            execution_time = round((datetime.utcnow() - start_time).total_seconds(), 2)

        report = {
            "task_id": task_id,
            "goal": goal,
            "success": success,
            "summary": summary,
            "extracted_data": extracted_data,
            "failure_reason": failure_reason,
            "execution_time_seconds": execution_time,
            "pages_visited": pages_visited or [],
            "action_count": action_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        logger.info(f"Generated Result Report for task {task_id}: Success={success}")
        return report


result_reporter = ResultReporter()
