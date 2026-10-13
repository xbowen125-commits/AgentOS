"""Tool contract injection and planner execution coverage."""

from pathlib import Path

import pytest

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.core.state import AgentState
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.prompt import build_planner_prompt
from agentos.planner.tool_prompt import (
    CALCULATOR_DESCRIPTION,
    ToolDescription,
    build_tool_prompt,
)
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry


def test_prompt_contains_calculator_contract_and_observation_rules() -> None:
    prompt = build_planner_prompt(AgentState("calculate"), [CALCULATOR_DESCRIPTION])
    assert "Available Tools:" in prompt
    assert "tool name: calculator" in prompt
    assert '"expression": {"type": "string"' in prompt
    assert '"required": ["expression"]' in prompt
    assert '"additionalProperties": false' in prompt
    assert "exactly match" in prompt
    assert "Never invent tools" in prompt
    assert "copy the observation result exactly" in prompt


def test_arbitrary_tool_schema_can_be_injected() -> None:
    tool = ToolDescription("lookup", "Look up a public record.", {"key": "string"})
    prompt = build_tool_prompt([tool])
    assert "tool name: lookup" in prompt
    assert 'input schema: {"key": "string"}' in prompt
    assert "call calculator" not in prompt


def test_empty_tools_are_explicit() -> None:
    assert "None. Do not emit tool_call" in build_tool_prompt([])


@pytest.mark.asyncio
async def test_fake_model_end_to_end_uses_contract_and_observation(tmp_path: Path) -> None:
    class RecordingModel(FakeModel):
        def __init__(self) -> None:
            super().__init__([
                (
                    '{"type":"tool_call","tool_name":"calculator",'
                    '"arguments":{"expression":"123*456"}}'
                ),
                '{"type":"final","answer":"56088"}',
            ])
            self.prompts: list[str] = []

        async def generate(self, prompt: str) -> str:
            self.prompts.append(prompt)
            return await super().generate(prompt)

    model = RecordingModel()
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    agent = Agent(
        planner=ModelPlanner(model, tools=[CALCULATOR_DESCRIPTION]),
        tool_executor=ToolExecutor(registry),
        memory=JsonMemory(tmp_path / "memory.json"),
    )
    state = await agent.run("计算 123*456")
    assert state.finished
    assert state.history == [
        ToolCallDecision("calculator", {"expression": "123*456"}),
        Observation(success=True, result="56088"),
        FinalAnswerDecision("56088"),
    ]
    assert all("tool name: calculator" in prompt for prompt in model.prompts)
    assert '"result": "56088"' in model.prompts[1]
