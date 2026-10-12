"""Registry for tools available to an agent."""

from agentos.exceptions import ToolAlreadyRegisteredError, ToolNotFoundError
from agentos.interfaces.tool import Tool


class ToolRegistry:
    """Store tools by their unique names."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool, rejecting duplicate names."""
        if tool.name in self._tools:
            raise ToolAlreadyRegisteredError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Return a registered tool by name."""
        try:
            return self._tools[name]
        except KeyError as error:
            raise ToolNotFoundError(f"Tool not found: {name}") from error

    def list_tools(self) -> list[Tool]:
        """Return tools in registration order."""
        return list(self._tools.values())
