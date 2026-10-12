"""Safe execution boundary for tool calls."""

from dataclasses import dataclass
from typing import Any

from agentos.core.decision import ToolCallDecision
from agentos.exceptions import (
    ToolArgumentError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolRuntimeError,
)
from agentos.tools.registry import ToolRegistry


@dataclass(frozen=True)
class Observation:
    """Structured result of a tool execution attempt."""

    tool_name: str
    success: bool
    result: Any = None
    error: ToolRuntimeError | None = None


class ToolExecutor:
    """Resolve and execute tool decisions without leaking tool failures."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute(self, decision: ToolCallDecision) -> Observation:
        """Execute a tool call and return a success or error observation."""
        try:
            tool = self.registry.get(decision.tool_name)
        except ToolNotFoundError as error:
            return Observation(tool_name=decision.tool_name, success=False, error=error)

        try:
            result = await tool.execute(**decision.arguments)
        except TypeError as error:
            argument_error = ToolArgumentError(
                f"Invalid arguments for tool '{decision.tool_name}': {error}"
            )
            return Observation(
                tool_name=decision.tool_name,
                success=False,
                error=argument_error,
            )
        # A tool is an extension boundary: ordinary tool failures must become observations.
        except Exception as error:  # noqa: BLE001
            execution_error = ToolExecutionError(
                f"Tool '{decision.tool_name}' execution failed: {error}"
            )
            return Observation(
                tool_name=decision.tool_name,
                success=False,
                error=execution_error,
            )

        return Observation(tool_name=decision.tool_name, success=True, result=result)
