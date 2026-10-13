"""Read-only failure classification from public execution evidence."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from agentos.events import AgentEvent
from agentos.tracing import TraceRecord

if TYPE_CHECKING:
    from agentos.evaluation.result import EvaluationResult


class FailureCategory(str, Enum):
    PARSE_ERROR = "PARSE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    TOOL_FAILURE = "TOOL_FAILURE"
    TIMEOUT = "TIMEOUT"
    LOOP_DETECTED = "LOOP_DETECTED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    STATE_MISMATCH = "STATE_MISMATCH"


@dataclass(frozen=True)
class FailureAnalysis:
    """An observed failure, not a claim about the model's hidden reasoning.

    category=None represents an unclassified failure with insufficient evidence.
    step=None means no reliable step index was recorded.
    """

    category: FailureCategory | None
    step: int | None
    evidence: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value if self.category is not None else None
        return data


_ERROR_TYPES = {
    "ToolNotFoundError": FailureCategory.UNKNOWN_TOOL,
    "ToolArgumentError": FailureCategory.INVALID_ARGUMENT,
    "ToolExecutionError": FailureCategory.TOOL_FAILURE,
    "RuntimeTimeoutError": FailureCategory.TIMEOUT,
    "TimeoutError": FailureCategory.TIMEOUT,
    "JSONDecodeError": FailureCategory.PARSE_ERROR,
}
_EVENT_TYPES = {
    "planner.parse.failed": FailureCategory.PARSE_ERROR,
    "planner.validation.failed": FailureCategory.VALIDATION_ERROR,
    "runtime.timeout": FailureCategory.TIMEOUT,
    "model.timeout": FailureCategory.TIMEOUT,
    "tool.timeout": FailureCategory.TIMEOUT,
    "agent.loop.detected": FailureCategory.LOOP_DETECTED,
    "planner.recovery.failed": FailureCategory.RECOVERY_FAILED,
    "state.check.failed": FailureCategory.STATE_MISMATCH,
}


class FailureAnalyzer:
    """Return the last observed error for a failed/incomplete run.

    Completed successful runs return None even if a tool error was recovered.
    Terminal errors take precedence over earlier attempts. No loop is inferred
    from repeated tool names, and ambiguous PlannerOutputError stays unclassified.
    Explicit optional stage events are accepted but are not emitted by core today.
    """

    def analyze(
        self, trace: TraceRecord | Sequence[AgentEvent],
        result: "EvaluationResult | None" = None,
    ) -> FailureAnalysis | None:
        events = list(trace.events if isinstance(trace, TraceRecord) else trace)
        run_ids = {event.run_id for event in events}
        if isinstance(trace, TraceRecord):
            run_ids.add(trace.run_id)
        if len(run_ids) > 1:
            raise ValueError("Failure analysis requires events from one run")
        if result is not None:
            expected_run = result.evidence.get("run_id")
            if expected_run is not None and run_ids and expected_run not in run_ids:
                raise ValueError("Evaluation result and trace belong to different runs")
            if result.success:
                return None
            if result.failure_type == "goal_mismatch":
                return FailureAnalysis(
                    FailureCategory.STATE_MISMATCH, None, "Goal state does not match final state",
                    {"task_id": result.task_id, "checks": result.evidence.get("checks", [])},
                )
        terminal = next((e for e in reversed(events) if e.event_type in {
            "agent.failed", "agent.finished", "agent.completed",
        }), None)
        if (result is None and terminal is not None
                and terminal.event_type != "agent.failed"
                and terminal.payload.get("finished") is True
                and not any(e.event_type == "state.check.failed" for e in events)):
            return None
        candidate: FailureAnalysis | None = None
        last_step: int | None = None
        for index, event in enumerate(events):
            payload = event.payload
            step = payload.get("step")
            if isinstance(step, int) and not isinstance(step, bool) and step >= 0:
                last_step = step
            error_type = payload.get("error_type")
            category = _EVENT_TYPES.get(event.event_type)
            is_failure = (
                category is not None or event.event_type in {"agent.failed", "planner.failed"}
                or (event.event_type == "tool.finished" and payload.get("success") is False)
                or event.event_type == "planner.retry.failed"
            )
            if not is_failure:
                continue
            if category is None and isinstance(error_type, str):
                category = _ERROR_TYPES.get(error_type)
            retry_end = next((e.event_type for e in reversed(events[:index])
                              if e.event_type in {"planner.retry.failed",
                                                  "planner.retry.completed"}), None)
            if (event.event_type == "agent.failed" and error_type == "PlannerOutputError"
                    and retry_end == "planner.retry.failed"):
                category = FailureCategory.RECOVERY_FAILED
            message = payload.get("error_message")
            evidence = message if isinstance(message, str) and message else (
                f"{event.event_type}: {error_type or 'failure recorded without detailed content'}"
            )
            candidate = FailureAnalysis(category, last_step, evidence, {
                "run_id": event.run_id, "event_type": event.event_type, "event_index": index,
                "error_type": error_type, "tool_name": payload.get("tool_name"),
                "classification_available": category is not None,
            })
        if candidate is not None:
            return candidate
        if result is not None and not result.success:
            return FailureAnalysis(None, None, "Failed evaluation without classified trace evidence",
                                   {"failure_type": result.failure_type, "task_id": result.task_id})
        return None
