"""Integration tests for observable workflows composed from the existing Agent loop."""

import asyncio
import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from agentos.core.decision import ToolCallDecision
from agentos.events import AgentEvent, EventBus
from agentos.exceptions import PlannerOutputError
from agentos.interfaces.tool import Tool
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.tools.registry import ToolRegistry
from agentos.tracing.json_trace import JsonTraceStore
from agentos.workflow import Workflow, WorkflowResult


class PrefixTool(Tool):
    """Prepare text before handing it to another tool."""

    name = "prefix"
    description = "Prefix a message with prepared:."
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    async def execute(self, message: str) -> str:
        return f"prepared:{message}"


class UppercaseTool(Tool):
    """Convert a message to uppercase."""

    name = "uppercase"

    async def execute(self, message: str) -> str:
        return message.upper()


class RecoverableTool(PrefixTool):
    """Fail for one input and allow a subsequent corrected call."""

    name = "recoverable"

    async def execute(self, message: str) -> str:
        if message == "bad":
            raise RuntimeError("temporary failure")
        return message


class RecordingModel(FakeModel):
    """Record the public prompts delivered to a deterministic model."""

    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return await super().generate(prompt)


class ConcurrentModel(RecordingModel):
    """Respond from run-local prompt state rather than a shared response cursor."""

    def __init__(self) -> None:
        super().__init__(["unused"])

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        user_line = next(line for line in prompt.splitlines() if line.startswith("User input: "))
        user_input = json.loads(user_line.removeprefix("User input: "))
        history = json.loads(prompt.split("History: ", maxsplit=1)[1])
        await asyncio.sleep(0)
        if not history:
            return tool_output("prefix", user_input)
        return final_output(history[-1]["result"])


class FailingModel(FakeModel):
    async def generate(self, prompt: str) -> str:
        del prompt
        raise RuntimeError("backend unavailable")


def tool_output(name: str, message: str) -> str:
    return json.dumps({
        "type": "tool_call", "tool_name": name, "arguments": {"message": message},
    })


def final_output(answer: str) -> str:
    return json.dumps({"type": "final", "answer": answer})


def registry_with(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def workflow_events(events: list[AgentEvent], run_id: str) -> list[AgentEvent]:
    return [
        event for event in events
        if event.run_id == run_id and event.event_type.startswith("workflow.")
    ]


@pytest.mark.asyncio
async def test_workflow_runs_distinct_tools_and_injects_observations(tmp_path: Path) -> None:
    model = RecordingModel([
        tool_output("prefix", "hello"),
        tool_output("uppercase", "prepared:hello"),
        final_output("PREPARED:HELLO"),
    ])
    workflow = Workflow(
        model, registry_with(PrefixTool(), UppercaseTool()), JsonMemory(tmp_path / "memory.json"),
    )

    result = await workflow.run("Prepare and uppercase hello")

    assert result.finished is True
    assert result.answer == "PREPARED:HELLO"
    assert result.state.step_count == 3
    assert [step.index for step in result.steps] == [1, 2]
    assert [step.decision.tool_name for step in result.steps] == ["prefix", "uppercase"]
    assert [step.observation.result for step in result.steps] == ["prepared:hello", "PREPARED:HELLO"]
    assert "tool name: prefix" in model.prompts[0]
    assert "tool name: uppercase" in model.prompts[0]
    assert '"required": ["message"]' in model.prompts[0]
    assert '"type": "observation"' in model.prompts[1]
    assert '"result": "prepared:hello"' in model.prompts[1]


@pytest.mark.asyncio
async def test_workflow_recovers_after_tool_execution_failure(tmp_path: Path) -> None:
    model = RecordingModel([
        tool_output("recoverable", "bad"),
        tool_output("recoverable", "recovered"),
        final_output("recovered"),
    ])
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    workflow = Workflow(
        model, registry_with(RecoverableTool()), JsonMemory(tmp_path / "memory.json"), event_bus=bus,
    )

    result = await workflow.run("Recover after the first failed call")

    assert result.finished is True
    assert result.answer == "recovered"
    assert [step.observation.success for step in result.steps] == [False, True]
    assert result.steps[0].observation.error_type == "ToolExecutionError"
    assert '"success": false' in model.prompts[1]
    assert "temporary failure" in model.prompts[1]
    assert [event.event_type for event in workflow_events(events, result.state.run_id)] == [
        "workflow.started", "workflow.step.started", "workflow.step.failed",
        "workflow.step.started", "workflow.step.completed", "workflow.completed",
    ]


@pytest.mark.asyncio
async def test_workflow_persists_multistep_trace_without_payload_contents(tmp_path: Path) -> None:
    model = RecordingModel([
        tool_output("prefix", "secret-payload"),
        tool_output("uppercase", "prepared:secret-payload"),
        final_output("PREPARED:SECRET-PAYLOAD"),
    ])
    bus = EventBus()
    store = JsonTraceStore(tmp_path / "traces")
    bus.subscribe(store.append)
    workflow = Workflow(
        model, registry_with(PrefixTool(), UppercaseTool()), JsonMemory(tmp_path / "memory.json"),
        event_bus=bus,
    )

    result = await workflow.run("private-user-input")
    trace = store.load(result.state.run_id)

    tool_calls = [event for event in trace.events if event.event_type == "tool.called"]
    assert [event.payload["tool_name"] for event in tool_calls] == ["prefix", "uppercase"]
    assert [event.payload["step"] for event in tool_calls] == [1, 2]
    assert [event.event_type for event in workflow_events(trace.events, result.state.run_id)] == [
        "workflow.started", "workflow.step.started", "workflow.step.completed",
        "workflow.step.started", "workflow.step.completed", "workflow.completed",
    ]
    serialized = json.dumps([event.to_dict() for event in trace.events])
    assert "secret-payload" not in serialized
    assert "private-user-input" not in serialized
    assert "arguments" not in serialized
    assert len(list((tmp_path / "traces").glob("run_*.json"))) == 1


@pytest.mark.asyncio
async def test_workflow_repairs_unknown_tool_before_execution(tmp_path: Path) -> None:
    model = RecordingModel([
        tool_output("invented", "hello"), tool_output("prefix", "hello"),
        final_output("prepared:hello"),
    ])
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    workflow = Workflow(
        model, registry_with(PrefixTool()), JsonMemory(tmp_path / "memory.json"), event_bus=bus,
    )

    result = await workflow.run("Use the available prefix tool")

    assert result.answer == "prepared:hello"
    assert len(result.steps) == 1
    assert result.steps[0].decision.tool_name == "prefix"
    assert [event.payload["tool_name"] for event in events if event.event_type == "tool.called"] == [
        "prefix",
    ]
    assert any(event.event_type == "planner.retry.completed" for event in events)
    assert len(model.prompts) == 3


@pytest.mark.asyncio
async def test_workflow_with_empty_registry_rejects_tool_call(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    workflow = Workflow(
        FakeModel([tool_output("invented", "hello")]), ToolRegistry(),
        JsonMemory(tmp_path / "memory.json"), max_retries=0, event_bus=bus,
    )

    with pytest.raises(PlannerOutputError, match="available tool"):
        await workflow.run("Call an unavailable tool")

    assert not any(event.event_type == "tool.called" for event in events)
    assert any(event.event_type == "workflow.failed" for event in events)


@pytest.mark.asyncio
async def test_workflow_marks_step_limit_as_failure_not_completion(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    workflow = Workflow(
        FakeModel([tool_output("prefix", "loop")]), registry_with(PrefixTool()),
        JsonMemory(tmp_path / "memory.json"), max_steps=2, event_bus=bus,
    )

    result = await workflow.run("Exhaust the decision budget")

    assert result.finished is False
    assert result.answer is None
    assert result.state.step_count == 2
    assert len(result.steps) == 2
    selected_events = workflow_events(events, result.state.run_id)
    assert selected_events[-1].event_type == "workflow.failed"
    assert selected_events[-1].payload["reason"] == "step_limit"
    assert not any(event.event_type == "workflow.completed" for event in selected_events)


@pytest.mark.asyncio
async def test_workflow_reports_model_failure_and_preserves_exception(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    workflow = Workflow(
        FailingModel(["unused"]), registry_with(PrefixTool()),
        JsonMemory(tmp_path / "memory.json"), event_bus=bus,
    )

    with pytest.raises(RuntimeError, match="backend unavailable"):
        await workflow.run("Cannot reach the backend")

    failures = [event for event in events if event.event_type == "workflow.failed"]
    assert len(failures) == 1
    assert failures[0].payload == {"error_type": "RuntimeError"}
    assert not any(event.event_type == "workflow.completed" for event in events)


@pytest.mark.asyncio
async def test_workflow_continues_when_event_handler_fails(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []

    def fail_handler(event: AgentEvent) -> None:
        del event
        raise RuntimeError("trace unavailable")

    bus.subscribe(fail_handler)
    bus.subscribe(events.append)
    workflow = Workflow(
        FakeModel([tool_output("prefix", "hello"), final_output("prepared:hello")]),
        registry_with(PrefixTool()), JsonMemory(tmp_path / "memory.json"), event_bus=bus,
    )

    result = await workflow.run("Run with a broken observer")

    assert result.answer == "prepared:hello"
    assert any(event.event_type == "workflow.completed" for event in events)


@pytest.mark.asyncio
async def test_workflow_repeated_runs_keep_separate_state(tmp_path: Path) -> None:
    model = RecordingModel([
        tool_output("prefix", "first"), final_output("prepared:first"),
        tool_output("prefix", "second"), final_output("prepared:second"),
    ])
    workflow = Workflow(model, registry_with(PrefixTool()), JsonMemory(tmp_path / "memory.json"))

    first = await workflow.run("first")
    second = await workflow.run("second")

    assert first.state.run_id != second.state.run_id
    assert first.answer == "prepared:first"
    assert second.answer == "prepared:second"
    assert len(first.steps) == len(second.steps) == 1
    assert first.state.history is not second.state.history
    assert model.prompts[2].endswith("History: []")


@pytest.mark.asyncio
async def test_workflow_concurrent_runs_keep_events_and_steps_separate(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    workflow = Workflow(
        ConcurrentModel(), registry_with(PrefixTool()), JsonMemory(tmp_path / "memory.json"),
        event_bus=bus,
    )

    first, second = await asyncio.gather(workflow.run("first"), workflow.run("second"))

    assert first.state.run_id != second.state.run_id
    assert [first.answer, second.answer] == ["prepared:first", "prepared:second"]
    assert first.steps[0].decision.arguments == {"message": "first"}
    assert second.steps[0].decision.arguments == {"message": "second"}
    for result in (first, second):
        assert [event.event_type for event in workflow_events(events, result.state.run_id)] == [
            "workflow.started", "workflow.step.started", "workflow.step.completed",
            "workflow.completed",
        ]


@pytest.mark.asyncio
async def test_distinct_workflows_on_shared_bus_do_not_duplicate_events(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    first_workflow = Workflow(
        ConcurrentModel(), registry_with(PrefixTool()), JsonMemory(tmp_path / "first.json"),
        event_bus=bus,
    )
    second_workflow = Workflow(
        ConcurrentModel(), registry_with(PrefixTool()), JsonMemory(tmp_path / "second.json"),
        event_bus=bus,
    )

    results = await asyncio.gather(first_workflow.run("first"), second_workflow.run("second"))

    for result in results:
        assert len(workflow_events(events, result.state.run_id)) == 4
        assert result.finished is True


@pytest.mark.asyncio
async def test_workflow_step_serialization_preserves_snapshot(tmp_path: Path) -> None:
    workflow = Workflow(
        FakeModel([tool_output("prefix", "hello"), final_output("prepared:hello")]),
        registry_with(PrefixTool()), JsonMemory(tmp_path / "memory.json"),
    )
    result = await workflow.run("hello")
    step = result.steps[0]
    original_decision = result.state.history[0]
    assert isinstance(original_decision, ToolCallDecision)
    original_decision.arguments["message"] = "changed-in-state"

    document: dict[str, Any] = step.to_dict()
    assert json.loads(json.dumps(document)) == document
    assert document["decision"]["arguments"] == {"message": "hello"}
    assert document["observation"]["result"] == "prepared:hello"
    document["decision"]["arguments"]["message"] = "changed-in-document"
    assert step.decision.arguments == {"message": "hello"}


@pytest.mark.asyncio
async def test_reentrant_shared_bus_handler_does_not_claim_another_run(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    nested_result: WorkflowResult | None = None
    nested_started = False

    async def start_nested(event: AgentEvent) -> None:
        nonlocal nested_result, nested_started
        if event.event_type == "agent.started" and not nested_started:
            nested_started = True
            nested_result = await nested.run("inner")

    bus.subscribe(start_nested)
    bus.subscribe(events.append)
    outer = Workflow(
        ConcurrentModel(), registry_with(PrefixTool()), JsonMemory(tmp_path / "outer.json"),
        event_bus=bus,
    )
    nested = Workflow(
        ConcurrentModel(), registry_with(PrefixTool()), JsonMemory(tmp_path / "inner.json"),
        event_bus=bus,
    )
    outer_result = await outer.run("outer")
    assert nested_result is not None
    assert outer_result.answer == "prepared:outer"
    assert nested_result.answer == "prepared:inner"
    for result in (outer_result, nested_result):
        assert [event.event_type for event in workflow_events(events, result.state.run_id)] == [
            "workflow.started", "workflow.step.started", "workflow.step.completed",
            "workflow.completed",
        ]
