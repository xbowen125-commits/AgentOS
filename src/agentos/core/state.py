"""Run-scoped agent state."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Minimal state carried by an agent run."""

    user_input: str
    step_count: int = 0
    finished: bool = False
    history: list[Any] = field(default_factory=list)

