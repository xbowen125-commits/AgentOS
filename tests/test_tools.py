"""Tests for the tool registry and executor."""

import json
from typing import Any

import pytest

from agentos.core.decision import ToolCallDecision
from agentos.exceptions import ToolAlreadyRegisteredError
from agentos.interfaces.tool import Tool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry


class EchoTool(Tool):
    name = "echo"

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        if "text" not in arguments:
            raise TypeError("missing 'text'")

    async def execute(self, **kwargs: Any) -> Any:
        return kwargs["text"]


class FailingTool(Tool):
    name = "failing"

    async def execute(self, **kwargs: Any) -> Any:
        raise TypeError("internal type failure")


def test_registry_registers_and_gets_tool() -> None:
    registry = ToolRegistry()
    tool = EchoTool()

    registry.register(tool)

    assert registry.get("echo") is tool
    assert registry.list_tools() == [tool]


def test_registry_rejects_duplicate_name() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    with pytest.raises(ToolAlreadyRegisteredError, match="echo"):
        registry.register(EchoTool())


@pytest.mark.asyncio
async def test_executor_returns_error_for_missing_tool() -> None:
    executor = ToolExecutor(ToolRegistry())

    observation = await executor.execute(ToolCallDecision(tool_name="missing", arguments={}))

    assert observation.success is False
    assert observation.error_type == "ToolNotFoundError"
    assert observation.error_message == "Tool not found: missing"


@pytest.mark.asyncio
async def test_executor_captures_argument_error() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    executor = ToolExecutor(registry)

    observation = await executor.execute(ToolCallDecision(tool_name="echo", arguments={}))

    assert observation.success is False
    assert observation.error_type == "ToolArgumentError"
    assert observation.error_message is not None
    assert "missing 'text'" in observation.error_message


@pytest.mark.asyncio
async def test_executor_captures_tool_exception() -> None:
    registry = ToolRegistry()
    registry.register(FailingTool())
    executor = ToolExecutor(registry)

    observation = await executor.execute(ToolCallDecision(tool_name="failing", arguments={}))

    assert observation.success is False
    assert observation.error_type == "ToolExecutionError"
    assert observation.error_message is not None
    assert "TypeError: internal type failure" in observation.error_message
    assert json.loads(json.dumps(observation.to_dict())) == observation.to_dict()
