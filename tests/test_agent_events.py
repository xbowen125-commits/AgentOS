"""Tests for Agent integration with runtime observability events."""

from pathlib import Path
from typing import Any

import pytest

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.state import AgentState
from agentos.events import AgentEvent, EventBus
from agentos.interfaces.tool import Tool
from agentos.memory.json_memory import JsonMemory
from agentos.planner.planner import AgentDecision, Planner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from tests.fakes.fake_planner import FakePlanner


class EchoTool(Tool):
    """Return a deterministic value for event integration tests."""

    name = "echo"

    async def execute(self, **kwargs: Any) -> Any:
        return kwargs["text"]


class FailingPlanner(Planner):
    """Raise a deterministic failure from the planner boundary."""

    async def plan(self, state: AgentState) -> AgentDecision:
        del state
        raise RuntimeError("planner failed")


def build_agent(planner: Planner, tmp_path: Path, bus: EventBus) -> Agent:
    registry = ToolRegistry()
    registry.register(EchoTool())
    return Agent(
        planner=planner,
        tool_executor=ToolExecutor(registry),
        memory=JsonMemory(tmp_path / "memory.json"),
        event_bus=bus,
    )


@pytest.mark.asyncio
async def test_agent_emits_ordered_runtime_events(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    planner = FakePlanner(
        [
            ToolCallDecision("echo", {"text": "hello"}),
            FinalAnswerDecision("done"),
        ]
    )

    state = await build_agent(planner, tmp_path, bus).run("use a tool")

    assert [event.event_type for event in events] == [
        "agent.started",
        "planner.started",
        "model.called",
        "model.finished",
        "planner.finished",
        "tool.called",
        "tool.finished",
        "planner.started",
        "model.called",
        "model.finished",
        "planner.finished",
        "agent.finished",
    ]
    assert {event.run_id for event in events} == {state.run_id}
    assert events[6].payload["success"] is True


@pytest.mark.asyncio
async def test_agent_emits_failure_without_swallowing_runtime_error(tmp_path: Path) -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    agent = build_agent(FailingPlanner(), tmp_path, bus)

    with pytest.raises(RuntimeError, match="planner failed"):
        await agent.run("fail")

    assert events[-1].event_type == "agent.failed"
    assert events[-1].payload == {
        "error_type": "RuntimeError",
        "error_message": "planner failed",
    }
