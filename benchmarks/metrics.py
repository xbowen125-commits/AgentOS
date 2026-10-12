"""Aggregate metrics for AgentOS benchmark runs."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol


class MeasuredResult(Protocol):
    """Minimal result shape required for metric aggregation."""

    @property
    def success(self) -> bool: ...

    @property
    def latency(self) -> float: ...

    @property
    def model_calls(self) -> int: ...

    @property
    def tool_calls(self) -> int: ...


@dataclass(frozen=True)
class EvaluationMetrics:
    """Serializable aggregate measurements for one benchmark run."""

    total_cases: int
    successful_cases: int
    failed_cases: int
    success_rate: float
    average_latency: float
    average_model_calls: float
    average_tool_calls: float

    @classmethod
    def from_results(cls, results: Sequence[MeasuredResult]) -> "EvaluationMetrics":
        """Aggregate case results, returning zeroed averages for an empty suite."""
        total_cases = len(results)
        successful_cases = sum(result.success for result in results)
        failed_cases = total_cases - successful_cases
        if total_cases == 0:
            return cls(0, 0, 0, 0.0, 0.0, 0.0, 0.0)
        return cls(
            total_cases=total_cases,
            successful_cases=successful_cases,
            failed_cases=failed_cases,
            success_rate=successful_cases / total_cases,
            average_latency=sum(result.latency for result in results) / total_cases,
            average_model_calls=sum(result.model_calls for result in results) / total_cases,
            average_tool_calls=sum(result.tool_calls for result in results) / total_cases,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a representation accepted by standard JSON encoders."""
        return asdict(self)
