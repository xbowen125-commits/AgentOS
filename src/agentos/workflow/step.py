"""Public call/observation pairs from a workflow run."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from agentos.core.decision import ToolCallDecision
from agentos.core.observation import Observation


@dataclass(frozen=True)
class WorkflowStep:
    """A completed tool attempt; failed observations remain available for recovery."""

    index: int
    decision: ToolCallDecision
    observation: Observation

    def to_dict(self) -> dict[str, Any]:
        """Return public structured data without exposing mutable argument references."""
        return {
            "index": self.index,
            "decision": {
                "type": "tool_call",
                "tool_name": self.decision.tool_name,
                "arguments": deepcopy(self.decision.arguments),
            },
            "observation": self.observation.to_dict(),
        }
