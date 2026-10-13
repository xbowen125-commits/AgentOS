"""Public evidence classification and conservative handling of ambiguity."""

import json

import pytest

from agentos.evaluation.failure import FailureAnalyzer, FailureCategory
from agentos.evaluation.result import EvaluationResult
from agentos.events import AgentEvent
from agentos.tracing import TraceRecord


def event(name: str, **payload: object) -> AgentEvent:
    return AgentEvent.create(name, "one", payload)


@pytest.mark.parametrize("error,category", [
    ("ToolNotFoundError", FailureCategory.UNKNOWN_TOOL),
    ("ToolArgumentError", FailureCategory.INVALID_ARGUMENT),
    ("ToolExecutionError", FailureCategory.TOOL_FAILURE),
    ("RuntimeTimeoutError", FailureCategory.TIMEOUT),
])
def test_tool_failures(error: str, category: FailureCategory) -> None:
    analysis = FailureAnalyzer().analyze(TraceRecord("one", [event(
        "tool.finished", step=2, success=False, error_type=error,
        error_message="public failure evidence",
    )]))
    assert analysis is not None
    assert analysis.category == category
    assert analysis.step == 2
    assert analysis.evidence == "public failure evidence"
    json.dumps(analysis.to_dict())


@pytest.mark.parametrize("name,category", [
    ("planner.parse.failed", FailureCategory.PARSE_ERROR),
    ("planner.validation.failed", FailureCategory.VALIDATION_ERROR),
    ("runtime.timeout", FailureCategory.TIMEOUT),
    ("agent.loop.detected", FailureCategory.LOOP_DETECTED),
    ("planner.recovery.failed", FailureCategory.RECOVERY_FAILED),
    ("state.check.failed", FailureCategory.STATE_MISMATCH),
])
def test_explicit_stage_events(name: str, category: FailureCategory) -> None:
    analysis = FailureAnalyzer().analyze([event(name)])
    assert analysis is not None and analysis.category == category


def test_success_and_recovered_tool_failure() -> None:
    events = [event("tool.finished", success=False, error_type="ToolArgumentError"),
              event("agent.finished", finished=True)]
    assert FailureAnalyzer().analyze(events) is None
    assert FailureAnalyzer().analyze([]) is None


def test_ambiguous_planner_error_not_assumed_parse_error() -> None:
    analysis = FailureAnalyzer().analyze([event("agent.failed", error_type="PlannerOutputError")])
    assert analysis is not None and analysis.category is None


def test_retry_exhaustion_and_terminal_precedence() -> None:
    events = [event("planner.started", step=3), event("planner.retry.failed", attempt=1),
              event("agent.failed", error_type="PlannerOutputError")]
    analysis = FailureAnalyzer().analyze(events)
    assert analysis is not None
    assert analysis.category == FailureCategory.RECOVERY_FAILED
    assert analysis.step == 3


def test_state_result_integration_preserves_serialization() -> None:
    result = EvaluationResult("task", False, {"checks": []}, failure_type="goal_mismatch")
    original = result.to_dict()
    analysis = result.analyze_failure(TraceRecord("one"))
    assert analysis is not None and analysis.category == FailureCategory.STATE_MISMATCH
    assert result.to_dict() == original


def test_mixed_run_rejected() -> None:
    with pytest.raises(ValueError, match="one run"):
        FailureAnalyzer().analyze([event("agent.started"),
                                   AgentEvent.create("agent.failed", "two")])


def test_repetition_and_step_limit_are_not_loop_proof() -> None:
    events = [event("tool.called", tool_name="calculator") for _ in range(4)]
    events.append(event("agent.finished", finished=False))
    assert FailureAnalyzer().analyze(events) is None
