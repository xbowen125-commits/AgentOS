"""Decision semantics, tool schemas, and guarded planner recovery."""

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
from agentos.planner.tool_prompt import CALCULATOR_DESCRIPTION, ToolDescription
from agentos.planner.validator import DecisionValidator
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry


def calculator_validator() -> DecisionValidator:
    return DecisionValidator([CALCULATOR_DESCRIPTION], required_tool="calculator")


def completed_state() -> AgentState:
    return AgentState("计算 123*456", history=[
        ToolCallDecision("calculator", {"expression": "123*456"}),
        Observation(success=True, result="56088"),
    ])


def test_valid_tool_call_is_returned_unchanged() -> None:
    decision = ToolCallDecision("calculator", {"expression": "123*456"})
    assert calculator_validator().validate(decision, AgentState("calculate")) is decision


@pytest.mark.parametrize("decision", [
    ToolCallDecision("calculate", {"expression": "123*456"}),
    ToolCallDecision("Calculator", {"expression": "123*456"}),
    ToolCallDecision("calculator", {}),
    ToolCallDecision("calculator", {"expression": 123}),
    ToolCallDecision("calculator", {"expression": "1+1", "extra": True}),
    ToolCallDecision("calculator", {"expression": "1" * 201}),
])
def test_invalid_tool_contract_is_rejected(decision: ToolCallDecision) -> None:
    with pytest.raises(PlannerOutputError):
        calculator_validator().validate(decision, AgentState("calculate"))


def test_empty_registry_rejects_unknown_tool() -> None:
    with pytest.raises(PlannerOutputError):
        DecisionValidator([]).validate(ToolCallDecision("calculator", {}), AgentState("task"))


def test_premature_final_is_rejected() -> None:
    with pytest.raises(PlannerOutputError, match="requires a successful"):
        calculator_validator().validate(FinalAnswerDecision("56088"), AgentState("calculate"))


@pytest.mark.parametrize("answer", ["", "   ", "51888", "答案是 56088"])
def test_invalid_final_is_rejected(answer: str) -> None:
    with pytest.raises(PlannerOutputError):
        calculator_validator().validate(FinalAnswerDecision(answer), completed_state())


def test_observation_grounded_final_is_returned_unchanged() -> None:
    decision = FinalAnswerDecision("56088")
    assert calculator_validator().validate(decision, completed_state()) is decision


@pytest.mark.parametrize("history", [
    [Observation(success=True, result="56088")],
    [ToolCallDecision("other", {}), Observation(success=True, result="56088")],
    [ToolCallDecision("calculator", {}), Observation(success=False, error_message="failure")],
    [ToolCallDecision("calculator", {})],
])
def test_missing_failed_or_unrelated_observation_cannot_support_final(history: list) -> None:
    with pytest.raises(PlannerOutputError):
        calculator_validator().validate(FinalAnswerDecision("56088"), AgentState("task", history=history))


def test_latest_failed_or_pending_call_does_not_reuse_old_success() -> None:
    state = completed_state()
    state.history.append(ToolCallDecision("calculator", {"expression": "1/0"}))
    with pytest.raises(PlannerOutputError):
        calculator_validator().validate(FinalAnswerDecision("56088"), state)
    state.history.append(Observation(success=False))
    with pytest.raises(PlannerOutputError):
        calculator_validator().validate(FinalAnswerDecision("56088"), state)


def test_non_tool_task_can_finish_without_observation() -> None:
    assert DecisionValidator([]).validate(FinalAnswerDecision("Hello"), AgentState("greet")) == (
        FinalAnswerDecision("Hello")
    )


def test_required_tool_policy_must_reference_declared_tool() -> None:
    with pytest.raises(ValueError):
        DecisionValidator([], required_tool="calculator")


def test_boolean_is_not_a_schema_integer() -> None:
    tool = ToolDescription("lookup", "lookup", {
        "type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"],
    })
    with pytest.raises(PlannerOutputError):
        DecisionValidator([tool]).validate(ToolCallDecision("lookup", {"id": True}), AgentState("task"))


@pytest.mark.asyncio
async def test_planner_repairs_premature_and_wrong_final_before_agent_sees_them(tmp_path: Path) -> None:
    model = FakeModel([
        '{"type":"final","answer":"51888"}',
        '{"type":"tool_call","tool_name":"calculator","arguments":{"expression":"123*456"}}',
        '{"type":"final","answer":"51888"}',
        '{"type":"final","answer":"56088"}',
    ])
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    agent = Agent(
        planner=ModelPlanner(model, [CALCULATOR_DESCRIPTION], required_tool="calculator"),
        tool_executor=ToolExecutor(registry),
        memory=JsonMemory(tmp_path / "memory.json"),
    )
    state = await agent.run("计算 123*456")
    assert state.finished
    assert state.history == completed_state().history + [FinalAnswerDecision("56088")]


@pytest.mark.asyncio
async def test_valid_json_with_content_instead_of_answer_is_still_rejected() -> None:
    planner = ModelPlanner(FakeModel(['{"type":"final","content":"51888"}']), max_retries=0)
    with pytest.raises(PlannerOutputError, match="answer"):
        await planner.plan(AgentState("task"))
