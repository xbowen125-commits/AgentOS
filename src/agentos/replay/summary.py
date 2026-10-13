"""Run summaries derived from existing trace and evaluation evidence."""

from dataclasses import asdict, dataclass
from typing import Any

from agentos.evaluation import EvaluationMetrics, Evaluator, ExpectedResult
from agentos.tracing import TraceRecord


def trace_final_result(trace: TraceRecord) -> str | None:
    """Read only explicitly recorded public answers, never infer them from tools."""
    for event in reversed(trace.events):
        if event.event_type in ("agent.finished", "agent.completed", "workflow.completed"):
            answer = event.payload.get("final_answer")
            if isinstance(answer, str):
                return answer
        if event.event_type in ("planner.finished", "planner.decision"):
            decision = event.payload.get("decision")
            if isinstance(decision, dict) and decision.get("type") == "final":
                answer = decision.get("answer")
                if isinstance(answer, str):
                    return answer
    return None


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    latency: float
    model_calls: int
    tool_calls: int
    retry_count: int
    validation_failure: bool
    final_result: str | None
    status: str
    tool_failures: int
    issues: tuple[str, ...]
    evaluation_metrics: EvaluationMetrics

    @classmethod
    def from_trace(
        cls,
        trace: TraceRecord,
        *,
        actual_answer: str | None = None,
        expected_result: ExpectedResult | str | None = None,
    ) -> "RunSummary":
        if actual_answer is not None and not isinstance(actual_answer, str):
            raise TypeError("Actual answer must be a string or None")
        recorded_answer = trace_final_result(trace)
        if actual_answer is not None and recorded_answer is not None and actual_answer != recorded_answer:
            raise ValueError("Supplied answer conflicts with the trace's recorded final answer")
        answer = recorded_answer if actual_answer is None else actual_answer
        # Without an expectation, answer correctness remains unassessed.
        assessment = Evaluator().evaluate(
            trace,
            ExpectedResult("") if expected_result is None else expected_result,
            actual_answer=None if expected_result is None else answer,
        )
        failed = any(
            event.event_type in ("agent.failed", "workflow.failed") for event in trace.events
        )
        completed = not failed and any(
            (event.event_type in ("agent.finished", "agent.completed")
             and event.payload.get("finished") is True)
            or event.event_type == "workflow.completed"
            for event in trace.events
        )
        calls = sum(event.event_type == "model.called" for event in trace.events)
        streams = sum(event.event_type == "stream.started" for event in trace.events)
        model_calls = calls + assessment.retry_attempts if calls else (streams or assessment.retry_attempts)
        issues = [issue for issue in assessment.issues if issue != "actual_answer_unavailable"]
        if completed and answer is None:
            issues.append("final_result_unavailable")
        return cls(
            run_id=trace.run_id,
            latency=assessment.latency,
            model_calls=model_calls,
            tool_calls=len(assessment.tool_names),
            retry_count=assessment.retry_attempts,
            validation_failure=assessment.validation_failed,
            final_result=answer,
            status="failed" if failed else ("completed" if completed else "incomplete"),
            tool_failures=assessment.tool_failures,
            issues=tuple(issues),
            evaluation_metrics=EvaluationMetrics.from_results([assessment]),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
