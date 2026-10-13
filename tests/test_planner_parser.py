"""Normalization and malformed-output coverage for Qwen-style decisions."""

import pytest

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.state import AgentState
from agentos.exceptions import PlannerOutputError
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.parser import parse_decision


@pytest.mark.parametrize(
    "output",
    [
        '{"name":"calculator","input":"123*456"}',
        '```json\n{"name":"calculator","input":"123*456"}\n```',
        '我将调用工具。\n{"name":"calculator","input":"123*456"}\n计算后回答。',
        '{"type":"tool_call","tool_name":"calculator","input":"123*456"}',
        '{"name":"calculator","input":{"expression":"123*456"}}',
    ],
)
def test_qwen_tool_output(output: str) -> None:
    assert parse_decision(output) == ToolCallDecision("calculator", {"expression": "123*456"})


def test_missing_arguments_default_to_empty_object() -> None:
    assert parse_decision('{"type":"tool_call","tool_name":"calculator"}') == (
        ToolCallDecision("calculator", {})
    )


def test_nested_objects_and_braces_in_strings() -> None:
    assert parse_decision('Result: ```json\n{"type":"final","answer":"{56088}"}\n```') == (
        FinalAnswerDecision("{56088}")
    )


@pytest.mark.parametrize(
    "output",
    [
        "not JSON",
        '{"type":"final","answer":}',
        '{"type":"tool_call","arguments":{"expression":"1+1"}',
        '{"type":"final","answer":"2"} {"type":"final","answer":"3"}',
        '[]',
        '{"type":"tool_call","tool_name":"calculator","arguments":null}',
        '{"name":"unknown","input":"123*456"}',
        '{"type":"final"}',
        '{"type":"other"}',
    ],
)
def test_invalid_or_ambiguous_output_is_rejected(output: str) -> None:
    with pytest.raises(PlannerOutputError):
        parse_decision(output)


@pytest.mark.asyncio
async def test_model_planner_uses_normalization() -> None:
    planner = ModelPlanner(FakeModel(['```json\n{"name":"calculator","input":"123*456"}\n```']))
    assert await planner.plan(AgentState("calculate")) == ToolCallDecision(
        "calculator", {"expression": "123*456"}
    )
