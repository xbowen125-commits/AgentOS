"""Tool interface."""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Abstract tool callable by an agent."""

    name: str

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        """Validate arguments before execution.

        Tools with an argument contract can override this hook. The default
        accepts any keyword arguments for backward-compatible simple tools.
        """

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with keyword arguments."""

