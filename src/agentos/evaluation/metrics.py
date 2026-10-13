"""Aggregate evaluation rates with explicit coverage and denominators."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol


class MeasuredResult(Protocol):
    @property
    def task_success(self) -> bool | None: ...

    @property
    def tool_matches(self) -> int | None: ...

    @property
    def tool_slots(self) -> int | None: ...

    @property
    def workflow_completed(self) -> bool | None: ...

    @property
    def latency(self) -> float: ...

    @property
    def retry_attempts(self) -> int: ...

    @property
    def validation_failed(self) -> bool: ...


@dataclass(frozen=True)
class EvaluationMetrics:
    """JSON-compatible rates; unobservable or inapplicable rates are None."""

    task_success_rate: float | None
    tool_selection_accuracy: float | None
    workflow_completion_rate: float | None
    average_latency: float
    retry_rate: float
    validation_failure_rate: float
    total_runs: int
    assessed_tasks: int
    assessed_tool_runs: int
    workflow_runs: int

    @classmethod
    def from_results(cls, results: Sequence[MeasuredResult]) -> "EvaluationMetrics":
        tasks = [result.task_success for result in results if result.task_success is not None]
        tools = [result for result in results if result.tool_slots is not None]
        workflows = [
            result.workflow_completed for result in results if result.workflow_completed is not None
        ]
        slots = sum(result.tool_slots or 0 for result in tools)
        matches = sum(result.tool_matches or 0 for result in tools)
        total = len(results)
        return cls(
            task_success_rate=sum(bool(value) for value in tasks) / len(tasks) if tasks else None,
            tool_selection_accuracy=(matches / slots if slots else 1.0) if tools else None,
            workflow_completion_rate=(
                sum(bool(value) for value in workflows) / len(workflows) if workflows else None
            ),
            average_latency=sum(result.latency for result in results) / total if total else 0.0,
            retry_rate=sum(result.retry_attempts > 0 for result in results) / total if total else 0.0,
            validation_failure_rate=(
                sum(result.validation_failed for result in results) / total if total else 0.0
            ),
            total_runs=total,
            assessed_tasks=len(tasks),
            assessed_tool_runs=len(tools),
            workflow_runs=len(workflows),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
