"""
State Machines and Enums for Task Lifecycle, Human Intervention, and URL Provenance.
"""
from enum import Enum
from typing import Set, Dict


class TaskStatus(str, Enum):
    """
    Task Lifecycle States.
    """
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Allowed Transitions Map
ALLOWED_TASK_TRANSITIONS: Dict[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.PLANNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.WAITING_FOR_HUMAN, TaskStatus.PAUSED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.OBSERVING, TaskStatus.WAITING_FOR_HUMAN, TaskStatus.PAUSED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.OBSERVING: {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.WAITING_FOR_HUMAN, TaskStatus.PAUSED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.WAITING_FOR_HUMAN: {TaskStatus.RUNNING, TaskStatus.PLANNING, TaskStatus.PAUSED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.PAUSED: {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


def validate_task_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """
    Validate if transitioning from current to target status is valid.
    """
    if current == target:
        return True
    return target in ALLOWED_TASK_TRANSITIONS.get(current, set())


class HumanInterventionType(str, Enum):
    """
    Type of Human Intervention requested.
    """
    CAPTCHA = "CAPTCHA"
    FORM_INPUT_REQUIRED = "FORM_INPUT_REQUIRED"
    FILE_UPLOAD_REQUIRED = "FILE_UPLOAD_REQUIRED"
    ACCOUNT_LOGIN_REQUIRED = "ACCOUNT_LOGIN_REQUIRED"
    SENSITIVE_ACTION = "SENSITIVE_ACTION"
    AMBIGUOUS_ACTION = "AMBIGUOUS_ACTION"


class HumanInterventionStatus(str, Enum):
    """
    Status of Human Intervention request.
    """
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


class URLProvenanceSource(str, Enum):
    """
    Allowed URL Provenance Sources.
    Must be tracked by URLPolicyGuard to prevent hallucinated URLs.
    """
    USER = "user"
    SEARCH_RESULT = "search_result"
    BROWSER_LINK = "browser_link"
    BROWSER_REDIRECT = "browser_redirect"
    FORBIDDEN = "forbidden"  # Reproaches LLM generated / guessed / fabricated domain
