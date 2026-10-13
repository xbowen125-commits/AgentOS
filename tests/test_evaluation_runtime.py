"""Independent state evaluation and existing Agent integration."""

import json
from pathlib import Path

import pytest

from agentos.core.agent import Agent
from agentos.core.state import AgentState as RuntimeState
from agentos.evaluation import EvaluationRunner, EvaluationState, EvaluationTask, StateChecker
from agentos.events import EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore
from examples.evaluation_demo import SetStatusTool


def test_task_creation_and_copy() -> None:
    initial = {"nested": [1]}
    task = EvaluationTask("one", "test", initial, {"done": True})
    initial["nested"].append(2)
    assert task.initial_state == {"nested": [1]}
    assert task.metadata == {}
    with pytest.raises(ValueError):
        EvaluationTask("", "test", {}, {})


def test_state_operations_are_isolated() -> None:
    state = EvaluationState({"nested": [1]})
    state.get("nested").append(2)
    state.snapshot()["nested"].append(3)
    state.update({"done": True})
    assert state.snapshot() == {"nested": [1], "done": True}
    assert state.get("missing", "default") == "default"
    state.reset({})
    assert state.snapshot() == {}


@pytest.mark.parametrize("final,success", [
    ({"done": True, "other": 1}, True), ({"done": False}, False),
    ({"done": 1}, False), ({}, False),
])
def test_checker(final: dict, success: bool) -> None:
    result = StateChecker().check(EvaluationTask("one", "test", {}, {"done": True}), final)
    assert result.success is success
    assert result.evidence["checks"][0]["matched"] is success
    json.dumps(result.to_dict())


@pytest.mark.asyncio
async def test_runner_existing_agent_and_trace(tmp_path: Path) -> None:
    state = EvaluationState()
    bus = EventBus()
    traces = JsonTraceStore(tmp_path / "traces")
    bus.subscribe(traces.append)
    registry = ToolRegistry()
    registry.register(SetStatusTool(state))
    model = FakeModel([
        '{"type":"tool_call","tool_name":"set_status","arguments":{"status":"done"}}',
        '{"type":"final","answer":"different text"}',
    ])
    agent = Agent(ModelPlanner.from_registry(model, registry), ToolExecutor(registry),
                  JsonMemory(tmp_path / "memory.json"), event_bus=bus)
    result = await EvaluationRunner(state, trace_store=traces).run(
        EvaluationTask("one", "Set status", {"status": "new"}, {"status": "done"}), agent,
    )
    assert result.success
    assert result.model_calls == 2
    assert result.tool_calls == 1
    assert result.latency >= 0


class StubAgent:
    def __init__(self, finished: bool = True, fail: bool = False) -> None:
        self.finished = finished
        self.fail = fail

    async def run(self, user_input: str) -> RuntimeState:
        if self.fail:
            raise ValueError("private error message")
        return RuntimeState(user_input, finished=self.finished)


@pytest.mark.asyncio
@pytest.mark.parametrize("agent,failure", [
    (StubAgent(), "goal_mismatch"), (StubAgent(False), "unfinished"),
    (StubAgent(fail=True), "runtime_error"),
])
async def test_runner_failure(agent: StubAgent, failure: str) -> None:
    result = await EvaluationRunner(EvaluationState()).run(
        EvaluationTask("one", "test", {}, {"done": True}), agent,
    )
    assert not result.success
    assert result.failure_type == failure
    assert result.model_calls is None
    assert "private error message" not in json.dumps(result.to_dict())
