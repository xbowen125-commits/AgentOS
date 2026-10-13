"""Read-only replay, evidence gaps, and failure/repair summary coverage."""

import json
from pathlib import Path

import pytest

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.core.state import AgentState
from agentos.evaluation import ExpectedResult
from agentos.events import AgentEvent
from agentos.exceptions import TraceFormatError, TraceNotFoundError
from agentos.replay import RunSummary, TraceReplay
from agentos.tracing import JsonTraceStore, TraceRecord


def make_trace(*entries: tuple[str, dict]) -> TraceRecord:
    return TraceRecord("replay-run", [
        AgentEvent(name, "replay-run", f"2026-01-01T00:00:{index:02d}+00:00", payload)
        for index, (name, payload) in enumerate(entries)
    ])


def successful_trace() -> TraceRecord:
    return make_trace(
        ("agent.started", {}),
        ("planner.started", {"step": 1}),
        ("model.called", {"step": 1}),
        ("model.finished", {"step": 1}),
        ("planner.finished", {"step": 1, "decision_type": "ToolCallDecision"}),
        ("planner.decision", {"step": 1, "decision_type": "ToolCallDecision"}),
        ("tool.called", {"step": 1, "tool_name": "calculator"}),
        ("tool.finished", {"step": 1, "tool_name": "calculator", "success": True}),
        ("planner.started", {"step": 2}),
        ("model.called", {"step": 2}),
        ("model.finished", {"step": 2}),
        ("planner.finished", {"step": 2, "decision_type": "FinalAnswerDecision"}),
        ("planner.decision", {"step": 2, "decision_type": "FinalAnswerDecision"}),
        ("agent.finished", {"finished": True, "step_count": 2}),
        ("agent.completed", {"finished": True, "step_count": 2}),
    )


def completed_state() -> AgentState:
    return AgentState(
        "private input", run_id="replay-run", step_count=2, finished=True,
        history=[
            ToolCallDecision("calculator", {"expression": "123*456"}),
            Observation(success=True, result="56088"),
            FinalAnswerDecision("56088"),
        ],
    )


def test_metadata_only_replay_marks_missing_content_and_deduplicates_aliases() -> None:
    result = TraceReplay().replay(successful_trace())
    assert [step.kind for step in result.steps] == [
        "model_call", "planner_decision", "tool_execution", "observation",
        "model_call", "planner_decision", "final_answer",
    ]
    assert len(result.events) == 15
    assert result.summary.status == "completed"
    assert result.summary.latency == 14
    assert result.summary.model_calls == 2
    assert result.summary.tool_calls == 1
    assert result.summary.final_result is None
    assert result.steps[-1].details["content_available"] is False
    assert result.summary.evaluation_metrics.task_success_rate is None
    assert "unavailable" in result.render_text()


def test_same_run_state_supplies_complete_public_steps() -> None:
    result = TraceReplay().replay(
        successful_trace(), state=completed_state(),
        expected_result=ExpectedResult("56088", ("calculator",)),
    )
    tool = next(step for step in result.steps if step.kind == "tool_execution")
    observation = next(step for step in result.steps if step.kind == "observation")
    assert tool.details["arguments"] == {"expression": "123*456"}
    assert observation.details["result"] == "56088"
    assert result.summary.final_result == "56088"
    assert result.summary.evaluation_metrics.task_success_rate == 1
    assert result.summary.evaluation_metrics.tool_selection_accuracy == 1
    assert "private input" not in result.render_text()
    assert json.loads(json.dumps(result.to_dict()))["summary"]["final_result"] == "56088"


def test_replay_by_store_id_and_portable_file_are_read_only(tmp_path: Path) -> None:
    store = JsonTraceStore(tmp_path / "traces")
    store.save(successful_trace())
    stored_path = next(store.directory.glob("run_*.json"))
    portable = tmp_path / "portable_trace.json"
    portable.write_bytes(stored_path.read_bytes())
    before = {path: path.read_bytes() for path in (stored_path, portable)}
    first = TraceReplay(store).replay("replay-run")
    second = TraceReplay().replay(portable)
    third = TraceReplay().replay(str(portable))
    assert first.to_dict() == second.to_dict() == third.to_dict()
    assert all(path.read_bytes() == content for path, content in before.items())
    assert len(list(store.directory.iterdir())) == 1


def test_replay_does_not_mutate_state_or_event_payloads() -> None:
    trace = successful_trace()
    state = completed_state()
    result = TraceReplay().replay(trace, state=state)
    tool = next(step for step in result.steps if step.kind == "tool_execution")
    tool.details["arguments"]["expression"] = "changed"
    result.events[0].payload["added"] = True
    assert state.history[0].arguments["expression"] == "123*456"
    assert trace.events[0].payload == {}


def test_retry_requests_are_included_in_model_call_count() -> None:
    trace = make_trace(
        ("agent.started", {}), ("planner.started", {"step": 1}),
        ("model.called", {"step": 1}), ("planner.retry.started", {"attempt": 1}),
        ("planner.retry.completed", {"attempt": 1}),
        ("model.finished", {"step": 1}),
        ("planner.finished", {"step": 1, "decision_type": "FinalAnswerDecision"}),
        ("agent.finished", {"finished": True, "step_count": 1}),
    )
    result = TraceReplay().replay(trace, actual_answer="done", expected_result="done")
    assert result.summary.model_calls == 2
    assert result.summary.retry_count == 1
    assert result.summary.validation_failure is True
    assert result.summary.status == "completed"
    assert result.summary.evaluation_metrics.retry_rate == 1
    assert result.summary.evaluation_metrics.task_success_rate == 1
    calls = [step for step in result.steps if step.kind == "model_call"]
    assert calls[-1].step_number == 1
    assert calls[-1].details["retry"] is True


def test_failed_run_preserves_failure_details_and_has_no_successful_final() -> None:
    trace = make_trace(
        ("agent.started", {}), ("model.called", {"step": 1}),
        ("agent.failed", {"error_type": "PlannerOutputError", "error_message": "Invalid decision"}),
    )
    result = TraceReplay().replay(trace, expected_result="done")
    assert result.summary.status == "failed"
    assert result.summary.validation_failure is True
    assert result.summary.final_result is None
    assert result.summary.evaluation_metrics.task_success_rate == 0
    assert result.steps[-1].details["error_type"] == "PlannerOutputError"
    assert not any(step.kind == "final_answer" for step in result.steps)


def test_tool_failure_can_be_recovered_in_a_workflow() -> None:
    trace = make_trace(
        ("agent.started", {}), ("workflow.started", {}),
        ("tool.called", {"step": 1, "tool_name": "calculator"}),
        ("tool.finished", {"step": 1, "success": False, "error_type": "ToolExecutionError"}),
        ("workflow.step.failed", {"step": 1}),
        ("tool.called", {"step": 2, "tool_name": "calculator"}),
        ("tool.finished", {"step": 2, "success": True}),
        ("agent.finished", {"finished": True}), ("workflow.completed", {}),
    )
    result = TraceReplay().replay(trace, actual_answer="2", expected_result="2")
    assert result.summary.status == "completed"
    assert result.summary.tool_calls == 2
    assert result.summary.tool_failures == 1
    assert result.summary.evaluation_metrics.workflow_completion_rate == 1
    assert len([step for step in result.steps if step.kind == "final_answer"]) == 1


def test_step_limit_is_incomplete_and_does_not_invent_final_answer() -> None:
    trace = make_trace(("agent.started", {}), ("agent.finished", {"finished": False}))
    result = TraceReplay().replay(trace)
    assert result.summary.status == "incomplete"
    assert not any(step.kind == "final_answer" for step in result.steps)


def test_summary_reads_explicit_recorded_answer_and_rejects_conflicts() -> None:
    trace = make_trace(
        ("agent.started", {}), ("agent.finished", {"finished": True, "final_answer": "done"}),
    )
    assert RunSummary.from_trace(trace).final_result == "done"
    with pytest.raises(ValueError, match="conflicts"):
        RunSummary.from_trace(trace, actual_answer="other")


def test_native_streams_are_counted_without_double_counting_agent_streams() -> None:
    trace = make_trace(
        ("stream.started", {}), ("model.completed", {}), ("stream.finished", {"status": "completed"}),
    )
    assert RunSummary.from_trace(trace).model_calls == 1
    agent_trace = make_trace(
        ("agent.started", {}), ("model.called", {}), ("stream.started", {}),
        ("model.completed", {}), ("stream.finished", {"status": "completed"}),
        ("agent.finished", {"finished": True}),
    )
    assert RunSummary.from_trace(agent_trace).model_calls == 1


@pytest.mark.parametrize("change", ["run_id", "tool", "observation", "answer"])
def test_mismatched_supplemental_state_is_rejected(change: str) -> None:
    state = completed_state()
    answer = None
    if change == "run_id":
        state.run_id = "foreign"
    elif change == "tool":
        state.history[0].tool_name = "foreign"
    elif change == "observation":
        state.history[1] = Observation(success=False)
    else:
        answer = "other"
    with pytest.raises(ValueError):
        TraceReplay().replay(successful_trace(), state=state, actual_answer=answer)


@pytest.mark.parametrize("document", [
    "not-json", "[]", '{"run_id":"one","events":{}}',
    '{"run_id":"one","events":[{}]}',
    '{"run_id":"one","events":[{"run_id":"two"}]}',
])
def test_invalid_trace_files_raise_clear_format_errors(tmp_path: Path, document: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(document, encoding="utf-8")
    with pytest.raises(TraceFormatError):
        TraceReplay().replay(path)


def test_missing_trace_and_missing_store_are_explicit(tmp_path: Path) -> None:
    with pytest.raises(TraceNotFoundError):
        TraceReplay().replay(tmp_path / "missing.json")
    with pytest.raises(ValueError, match="JsonTraceStore"):
        TraceReplay().replay("missing-run")
    with pytest.raises(TraceNotFoundError):
        TraceReplay(JsonTraceStore(tmp_path / "empty")).replay("missing-run")
