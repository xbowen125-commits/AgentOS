"""Trace evaluation for successful, failed, and recovered runtime executions."""

import json
from pathlib import Path

import pytest

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision
from agentos.evaluation import (
    EvaluationMetrics,
    Evaluator,
    ExpectedResult,
    render_markdown_report,
    write_markdown_report,
)
from agentos.events import AgentEvent, EventBus
from agentos.exceptions import PlannerOutputError
from agentos.interfaces.tool import Tool
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore, TraceRecord
from agentos.workflow import Workflow
from benchmarks.evaluator import load_cases


def trace_with(*events: tuple[str, dict]) -> TraceRecord:
    return TraceRecord("run-1", [
        AgentEvent(name, "run-1", f"2026-01-01T00:00:{index:02d}+00:00", payload)
        for index, (name, payload) in enumerate(events)
    ])


def call(expression: str) -> str:
    return json.dumps({
        "type": "tool_call", "tool_name": "calculator", "arguments": {"expression": expression},
    })


def final(answer: str) -> str:
    return json.dumps({"type": "final", "answer": answer})


def build_agent(tmp_path: Path, responses: list[str], max_retries: int = 2):
    store = JsonTraceStore(tmp_path / "traces")
    evaluator = Evaluator(store)
    bus = EventBus()
    evaluator.subscribe(bus)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    agent = Agent(
        planner=ModelPlanner.from_registry(
            FakeModel(responses), registry, max_retries=max_retries, event_bus=bus,
        ),
        tool_executor=ToolExecutor(registry),
        memory=JsonMemory(tmp_path / "memory.json"),
        event_bus=bus,
    )
    return agent, evaluator, store


@pytest.mark.asyncio
async def test_single_agent_success_reuses_saved_trace_and_benchmark_case(tmp_path: Path) -> None:
    case = load_cases()[0]
    agent, evaluator, store = build_agent(tmp_path, list(case.model_responses))
    state = await agent.run(case.input)
    decision = state.history[-1]
    assert isinstance(decision, FinalAnswerDecision)
    result = evaluator.evaluate_case(
        store.load(state.run_id), case,
        actual_answer=decision.answer, expected_tools=["calculator"],
    )
    assert result.task_success is True
    assert result.case_id == case.id
    assert result.tool_selection_accuracy == 1
    assert result.workflow_completed is None
    assert result.retry_attempts == result.tool_failures == 0
    assert result.validation_failed is False
    assert result.latency >= 0
    assert json.loads(json.dumps(result.to_dict()))["task_success"] is True


@pytest.mark.asyncio
async def test_workflow_success_counts_ordered_tools(tmp_path: Path) -> None:
    class FormatTool(Tool):
        """Format the calculator output."""

        name = "format"

        async def execute(self, value: str) -> str:
            return f"Result: {value}"

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(FormatTool())
    evaluator = Evaluator(JsonTraceStore(tmp_path / "traces"))
    bus = EventBus()
    evaluator.subscribe(bus)
    workflow = Workflow(
        FakeModel([
            call("123*456"),
            '{"type":"tool_call","tool_name":"format","arguments":{"value":"56088"}}',
            final("Result: 56088"),
        ]),
        registry, JsonMemory(tmp_path / "memory.json"), event_bus=bus,
    )
    outcome = await workflow.run("Calculate and format")
    result = evaluator.evaluate_run(
        outcome.state.run_id,
        ExpectedResult("Result: 56088", ("calculator", "format")),
        actual_answer=outcome.answer,
    )
    assert result.task_success is True
    assert result.workflow_completed is True
    assert result.tool_names == ("calculator", "format")
    assert result.tool_matches == result.tool_slots == 2


@pytest.mark.asyncio
async def test_tool_failure_and_task_mismatch_are_separate(tmp_path: Path) -> None:
    agent, evaluator, _ = build_agent(tmp_path, [call("1/0"), final("Cannot calculate")])
    state = await agent.run("calculate")
    result = evaluator.evaluate_run(
        state.run_id, ExpectedResult("2", ("calculator",)), actual_answer="Cannot calculate",
    )
    assert result.task_success is False
    assert result.tool_failures == 1
    assert result.tool_selection_accuracy == 1
    assert result.validation_failed is False
    assert "answer_mismatch" in result.issues


@pytest.mark.asyncio
async def test_retry_recovery_retains_validation_failure_evidence(tmp_path: Path) -> None:
    agent, evaluator, _ = build_agent(tmp_path, ["not-json", call("1+1"), final("2")])
    state = await agent.run("calculate")
    result = evaluator.evaluate_run(state.run_id, "2", actual_answer="2")
    metrics = EvaluationMetrics.from_results([result])
    assert result.task_success is True
    assert result.retry_attempts == 1
    assert result.validation_failed is True
    assert metrics.task_success_rate == metrics.retry_rate == metrics.validation_failure_rate == 1


@pytest.mark.asyncio
async def test_validation_failure_without_retries_is_detected(tmp_path: Path) -> None:
    agent, evaluator, store = build_agent(tmp_path, ["not-json"], max_retries=0)
    with pytest.raises(PlannerOutputError):
        await agent.run("calculate")
    path = next(store.directory.glob("run_*.json"))
    run_id = json.loads(path.read_text(encoding="utf-8"))["run_id"]
    result = evaluator.evaluate_run(run_id, "2")
    assert result.task_success is False
    assert result.retry_attempts == 0
    assert result.validation_failed is True


def test_finished_false_and_empty_trace_are_not_successes() -> None:
    trace = trace_with(("agent.started", {}), ("agent.finished", {"finished": False}))
    assert Evaluator().evaluate(trace, "2", actual_answer="2").task_success is False
    with pytest.raises(ValueError, match="non-empty"):
        Evaluator().evaluate(TraceRecord("empty"), "2")


def test_missing_answer_or_tool_expectations_remain_unassessed() -> None:
    trace = trace_with(("agent.started", {}), ("agent.finished", {"finished": True}))
    result = Evaluator().evaluate(trace, "2")
    metrics = EvaluationMetrics.from_results([result])
    assert result.task_success is None
    assert metrics.task_success_rate is None
    assert metrics.tool_selection_accuracy is None
    assert metrics.workflow_completion_rate is None
    assert metrics.assessed_tasks == metrics.assessed_tool_runs == 0
    assert "N/A" in render_markdown_report([result])


@pytest.mark.parametrize("expected, accuracy", [
    (("calculator", "format"), 1.0),
    (("format", "calculator"), 0.0),
    (("calculator",), 0.5),
    (("calculator", "format", "other"), 2 / 3),
    ((), 0.0),
])
def test_tool_accuracy_penalizes_order_extra_and_missing_calls(expected: tuple, accuracy: float) -> None:
    trace = trace_with(
        ("agent.started", {}), ("tool.called", {"tool_name": "calculator"}),
        ("tool.called", {"tool_name": "format"}), ("agent.finished", {"finished": True}),
    )
    result = Evaluator().evaluate(trace, ExpectedResult("done", expected), actual_answer="done")
    assert result.tool_selection_accuracy == pytest.approx(accuracy)


def test_metrics_aggregate_denominators_and_latency() -> None:
    evaluator = Evaluator()
    first = evaluator.evaluate(trace_with(
        ("agent.started", {}), ("tool.called", {"tool_name": "calculator"}),
        ("agent.finished", {"finished": True}),
    ), ExpectedResult("2", ("calculator",)), actual_answer="2")
    second = evaluator.evaluate(trace_with(
        ("agent.started", {}), ("workflow.started", {}),
        ("planner.retry.started", {"attempt": 1}), ("agent.failed", {"error_type": "PlannerOutputError"}),
        ("workflow.failed", {}),
    ), ExpectedResult("done", ("calculator",)), actual_answer=None)
    metrics = EvaluationMetrics.from_results([first, second])
    assert metrics.task_success_rate == 0.5
    assert metrics.tool_selection_accuracy == 0.5
    assert metrics.workflow_completion_rate == 0
    assert metrics.average_latency == 3
    assert metrics.retry_rate == metrics.validation_failure_rate == 0.5
    assert metrics.total_runs == 2
    assert metrics.assessed_tasks == 2
    assert metrics.workflow_runs == 1
    assert json.loads(json.dumps(metrics.to_dict())) == metrics.to_dict()


def test_empty_metrics_and_no_tool_task() -> None:
    metrics = EvaluationMetrics.from_results([])
    assert metrics.total_runs == 0
    assert metrics.task_success_rate is None
    assert metrics.average_latency == metrics.retry_rate == metrics.validation_failure_rate == 0
    result = Evaluator().evaluate(
        trace_with(("agent.started", {}), ("agent.finished", {"finished": True})),
        ExpectedResult("hello", ()), actual_answer="hello",
    )
    assert EvaluationMetrics.from_results([result]).tool_selection_accuracy == 1


def test_markdown_report_does_not_include_answers_or_prompts(tmp_path: Path) -> None:
    result = Evaluator().evaluate(
        trace_with(("agent.started", {}), ("agent.finished", {"finished": True})),
        "private-answer", actual_answer="private-answer", case_id="case|one",
    )
    path = write_markdown_report([result], tmp_path / "evaluation_report.md")
    report = path.read_text(encoding="utf-8")
    assert report.startswith("# AgentOS Evaluation Report")
    assert "Task Success Rate | 100.0%" in report
    assert "case\\|one" in report
    assert "private-answer" not in report


def test_foreign_run_events_are_rejected() -> None:
    trace = TraceRecord("one", [AgentEvent.create("agent.started", "two")])
    with pytest.raises(ValueError, match="different run"):
        Evaluator().evaluate(trace, "done")
