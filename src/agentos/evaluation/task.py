"""Tasks for the state-based evaluation prototype."""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationTask:
    """Describe public input and independent expected environment state."""

    task_id: str
    description: str
    initial_state: dict[str, Any]
    goal_state: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must not be empty")
        self.initial_state = deepcopy(self.initial_state)
        self.goal_state = deepcopy(self.goal_state)
        self.metadata = deepcopy(self.metadata)
