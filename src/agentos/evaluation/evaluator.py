"""Evaluate execution evidence without modifying runtime behavior or trace schemas."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from agentos.events import EventBus
from agentos.tracing import JsonTraceStore, TraceRecord
from agentos.tracing.metrics import RuntimeMetrics


class EvaluationCase(Protocol):
    """Structural interface compatible with existing BenchmarkCase objects."""

    @property
    def id(self) -> str: ...

    @property
    def expected_answer(self) -> str: ...


@dataclass(frozen=True)
class ExpectedResult:
    answer: str
    tool_names: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.answer, str):
            raise TypeError("Expected answer must be a string")
        if self.tool_names is not None:
            if isinstance(self.tool_names, str) or not all(
                isinstance(name, str) and name for name in self.tool_names
            ):
                raise TypeError("Expected tools must be a sequence of non-empty names")
            object.__setattr__(self, "tool_names", tuple(self.tool_names))


@dataclass(frozen=True)
class EvaluationResult:
    run_id: str
    case_id: str | None
    task_success: bool | None
    actual_answer: str | None
    expected_answer: str
    tool_names: tuple[str, ...]
    tool_matches: int | None
    tool_slots: int | None
    tool_selection_accuracy: float | None
    workflow_completed: bool | None
    latency: float
    retry_attempts: int
    validation_failed: bool
    tool_failures: int
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Evaluator:
    """Compare public run outcomes and expected tool sequences with saved traces."""

    def __init__(self, trace_store: JsonTraceStore | None = None) -> None:
        self.trace_store = trace_store

    def subscribe(self, event_bus: EventBus) -> None:
        """Attach the existing JSON trace adapter to a runtime's EventBus once."""
        if self.trace_store is None:
            raise ValueError("A JsonTraceStore is required to subscribe")
        event_bus.subscribe(self.trace_store.append)

    def evaluate_run(
        self,
        run_id: str,
        expected_result: ExpectedResult | str,
        *,
        actual_answer: str | None = None,
    ) -> EvaluationResult:
        if self.trace_store is None:
            raise ValueError("A JsonTraceStore is required to load a run")
        return self.evaluate(self.trace_store.load(run_id), expected_result, actual_answer=actual_answer)

    def evaluate_case(
        self,
        trace: TraceRecord,
        case: EvaluationCase,
        *,
        actual_answer: str | None = None,
        expected_tools: Sequence[str] | None = None,
    ) -> EvaluationResult:
        expected = ExpectedResult(
            case.expected_answer, None if expected_tools is None else tuple(expected_tools)
        )
        return self.evaluate(trace, expected, actual_answer=actual_answer, case_id=case.id)

    def evaluate(
        self,
        trace: TraceRecord,
        expected_result: ExpectedResult | str,
        *,
        actual_answer: str | None = None,
        case_id: str | None = None,
    ) -> EvaluationResult:
        """Score exact answers and ordered tool selections, retaining recovered failures.

        Answers are supplied by the caller, because runtime traces omit answer content.
        Retry started proves a preceding PlannerOutputError, including successful repairs.
        A failed tool alone does not imply task failure when the run later recovers.
        """
        if not trace.events:
            raise ValueError("Evaluation requires a non-empty runtime trace")
        if any(event.run_id != trace.run_id for event in trace.events):
            raise ValueError("Trace contains events from a different run")
        if actual_answer is not None and not isinstance(actual_answer, str):
            raise TypeError("Actual answer must be a string or None")
        expected = (
            ExpectedResult(expected_result) if isinstance(expected_result, str) else expected_result
        )
        runtime = RuntimeMetrics.from_trace(trace)
        events = trace.events
        failed = any(event.event_type in ("agent.failed", "workflow.failed") for event in events)
        completed = not failed and any(
            (
                event.event_type in ("agent.finished", "agent.completed")
                and event.payload.get("finished") is True
            ) or event.event_type == "workflow.completed"
            for event in events
        )
        task_success: bool | None = False
        if completed:
            task_success = None if actual_answer is None else actual_answer == expected.answer
        tools = tuple(
            str(event.payload.get("tool_name", ""))
            for event in events if event.event_type == "tool.called"
        )
        matches = None
        slots = None
        accuracy = None
        if expected.tool_names is not None:
            matches = sum(actual == target for actual, target in zip(tools, expected.tool_names))
            slots = max(len(tools), len(expected.tool_names))
            accuracy = matches / slots if slots else 1.0
        workflow = any(event.event_type.startswith("workflow.") for event in events)
        workflow_completed = None
        if workflow:
            workflow_completed = completed and any(
                event.event_type == "workflow.completed" for event in events
            )
        retries = sum(event.event_type == "planner.retry.started" for event in events)
        validation_failed = retries > 0 or any(
            event.event_type == "planner.validation.failed"
            or (
                event.event_type == "agent.failed"
                and event.payload.get("error_type") == "PlannerOutputError"
            ) for event in events
        )
        tool_failures = sum(
            event.event_type == "tool.finished" and event.payload.get("success") is False
            for event in events
        )
        issues: list[str] = []
        if not completed:
            issues.append("runtime_incomplete_or_failed")
        elif actual_answer is None:
            issues.append("actual_answer_unavailable")
        elif not task_success:
            issues.append("answer_mismatch")
        if accuracy is not None and accuracy < 1:
            issues.append("tool_sequence_mismatch")
        if tool_failures:
            issues.append("tool_failure")
        if validation_failed:
            issues.append("validation_failure")
        return EvaluationResult(
            run_id=trace.run_id,
            case_id=case_id,
            task_success=task_success,
            actual_answer=actual_answer,
            expected_answer=expected.answer,
            tool_names=tools,
            tool_matches=matches,
            tool_slots=slots,
            tool_selection_accuracy=accuracy,
            workflow_completed=workflow_completed,
            latency=runtime.total_latency,
            retry_attempts=retries,
            validation_failed=validation_failed,
            tool_failures=tool_failures,
            issues=tuple(issues),
        )
