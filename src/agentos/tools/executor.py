"""Safe execution boundary for tool calls."""

import json
from typing import Any

from agentos.core.decision import ToolCallDecision
from agentos.core.observation import Observation
from agentos.exceptions import (
    ToolArgumentError,
    ToolExecutionError,
    ToolNotFoundError,
)
from agentos.tools.registry import ToolRegistry


class ToolExecutor:
    """Resolve and execute tool decisions without leaking tool failures."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute(self, decision: ToolCallDecision) -> Observation:
        """Execute a tool call and return a serializable observation."""
        try:
            tool = self.registry.get(decision.tool_name)
        except ToolNotFoundError as error:
            return Observation(
                success=False,
                error_type=type(error).__name__,
                error_message=str(error),
            )

        try:
            tool.validate_arguments(decision.arguments)
        except ToolArgumentError as error:
            return Observation(
                success=False,
                error_type=type(error).__name__,
                error_message=str(error),
            )
        except (TypeError, ValueError) as error:
            return Observation(
                success=False,
                error_type=ToolArgumentError.__name__,
                error_message=f"Invalid arguments for tool '{decision.tool_name}': {error}",
            )
        except Exception as error:  # noqa: BLE001
            return Observation(
                success=False,
                error_type=ToolExecutionError.__name__,
                error_message=(
                    f"Argument validation for tool '{decision.tool_name}' failed with "
                    f"{type(error).__name__}: {error}"
                ),
            )

        try:
            result = await tool.execute(**decision.arguments)
            serialized_result = self._serialize_result(result)
        # A tool is an extension boundary: ordinary tool failures must become observations.
        except Exception as error:  # noqa: BLE001
            return Observation(
                success=False,
                error_type=ToolExecutionError.__name__,
                error_message=(
                    f"Tool '{decision.tool_name}' execution failed with "
                    f"{type(error).__name__}: {error}"
                ),
            )

        return Observation(success=True, result=serialized_result)

    @staticmethod
    def _serialize_result(result: Any) -> str | None:
        if result is None:
            return None
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(result)
