"""Tests for strict JSON decisions produced by ModelPlanner."""

import json
from pathlib import Path

import pytest

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.core.state import AgentState
from agentos.exceptions import PlannerOutputError
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.prompt import build_planner_prompt
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_model_planner_parses_tool_call() -> None:
    output = json.dumps(
        {
            "type": "tool_call",
            "tool_name": "calculator",
            "arguments": {"expression": "1+1"},
        }
    )
    planner = ModelPlanner(FakeModel([output]))

    decision = await planner.plan(AgentState(user_input="calculate"))

    assert decision == ToolCallDecision(
        tool_name="calculator",
        arguments={"expression": "1+1"},
    )


@pytest.mark.asyncio
async def test_model_planner_parses_final_answer() -> None:
    planner = ModelPlanner(FakeModel(['{"type":"final","answer":"2"}']))

    decision = await planner.plan(AgentState(user_input="answer"))

    assert decision == FinalAnswerDecision(answer="2")


@pytest.mark.asyncio
async def test_model_planner_rejects_invalid_json() -> None:
    planner = ModelPlanner(FakeModel(["final answer: 2"]))

    with pytest.raises(PlannerOutputError, match="not valid JSON"):
        await planner.plan(AgentState(user_input="answer"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output", "missing_field"),
    [
        ('{"type":"tool_call","arguments":{}}', "tool_name"),
        ('{"type":"final"}', "answer"),
    ],
)
async def test_model_planner_rejects_missing_fields(output: str, missing_field: str) -> None:
    planner = ModelPlanner(FakeModel([output]))

    with pytest.raises(PlannerOutputError, match=missing_field):
        await planner.plan(AgentState(user_input="answer"))


@pytest.mark.asyncio
async def test_model_planner_rejects_unknown_type() -> None:
    planner = ModelPlanner(FakeModel(['{"type":"reasoning","content":"hidden"}']))

    with pytest.raises(PlannerOutputError, match="Unknown decision type"):
        await planner.plan(AgentState(user_input="answer"))


def test_planner_prompt_contains_public_state_only() -> None:
    state = AgentState(
        user_input="calculate 1+1",
        history=[
            ToolCallDecision("calculator", {"expression": "1+1"}),
            Observation(success=True, result="2"),
        ],
    )

    prompt = build_planner_prompt(state)

    assert "calculate 1+1" in prompt
    assert '"expression": "1+1"' in prompt
    assert '"type": "observation"' in prompt
    assert "reasoning" not in prompt.lower()


@pytest.mark.asyncio
async def test_agent_accepts_model_backed_planner(tmp_path: Path) -> None:
    planner = ModelPlanner(FakeModel(['{"type":"final","answer":"complete"}']))
    agent = Agent(
        planner=planner,
        tool_executor=ToolExecutor(ToolRegistry()),
        memory=JsonMemory(tmp_path / "memory.json"),
    )

    state = await agent.run("finish")

    assert state.finished is True
    assert state.history == [FinalAnswerDecision(answer="complete")]
