"""Tests for the minimal Agent runtime loop."""

from typing import Any

import pytest

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.exceptions import ToolNotFoundError
from agentos.interfaces.memory import Memory
from agentos.interfaces.tool import Tool
from agentos.planner.planner import AgentDecision
from agentos.tools.executor import Observation
from tests.fakes.fake_model import FakeModel
from tests.fakes.fake_planner import FakePlanner


class FakeMemory(Memory):
    """Minimal memory dependency that is not used by the Step 3 loop."""

    def store(self, data: dict[str, Any]) -> None:
        pass

    def retrieve(self) -> None:
        return None


class EchoTool(Tool):
    """Echo its input so the loop can record a deterministic observation."""

    name = "echo"

    async def execute(self, **kwargs: Any) -> Any:
        return kwargs["text"]


def build_agent(
    planner: FakePlanner,
    *,
    tools: list[Tool] | None = None,
    max_steps: int = 10,
) -> Agent:
    return Agent(
        model=FakeModel(),
        planner=planner,
        tools=tools or [],
        memory=FakeMemory(),
        max_steps=max_steps,
    )


@pytest.mark.asyncio
async def test_agent_stops_on_final_answer() -> None:
    decision = FinalAnswerDecision(answer="done")
    agent = build_agent(FakePlanner([decision]))

    state = await agent.run("hello")

    assert state.user_input == "hello"
    assert state.step_count == 1
    assert state.finished is True
    assert state.history == [decision]


@pytest.mark.asyncio
async def test_agent_executes_tool_and_continues_planning() -> None:
    tool_decision = ToolCallDecision(tool_name="echo", arguments={"text": "observation"})
    final_decision = FinalAnswerDecision(answer="complete")
    agent = build_agent(FakePlanner([tool_decision, final_decision]), tools=[EchoTool()])

    state = await agent.run("use a tool")

    assert state.step_count == 2
    assert state.finished is True
    assert state.history == [
        tool_decision,
        Observation(tool_name="echo", success=True, result="observation"),
        final_decision,
    ]


@pytest.mark.asyncio
async def test_agent_stops_at_max_steps() -> None:
    decisions: list[AgentDecision] = [
        ToolCallDecision(tool_name="echo", arguments={"text": "first"}),
        ToolCallDecision(tool_name="echo", arguments={"text": "second"}),
        FinalAnswerDecision(answer="not reached"),
    ]
    agent = build_agent(FakePlanner(decisions), tools=[EchoTool()], max_steps=2)

    state = await agent.run("bounded task")

    assert state.step_count == 2
    assert state.finished is False
    assert state.history == [
        decisions[0],
        Observation(tool_name="echo", success=True, result="first"),
        decisions[1],
        Observation(tool_name="echo", success=True, result="second"),
    ]


@pytest.mark.asyncio
async def test_agent_continues_after_tool_error() -> None:
    tool_decision = ToolCallDecision(tool_name="missing", arguments={})
    final_decision = FinalAnswerDecision(answer="recovered")
    agent = build_agent(FakePlanner([tool_decision, final_decision]))

    state = await agent.run("recover from a tool error")

    observation = state.history[1]
    assert isinstance(observation, Observation)
    assert observation.success is False
    assert isinstance(observation.error, ToolNotFoundError)
    assert state.finished is True
    assert state.history[-1] == final_decision
