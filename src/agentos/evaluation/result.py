"""State-evaluation results; separate from the v1 trace result."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class EvaluationResult:
    task_id: str
    success: bool
    evidence: dict[str, Any]
    latency: float = 0.0
    model_calls: int | None = None
    tool_calls: int | None = None
    failure_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
