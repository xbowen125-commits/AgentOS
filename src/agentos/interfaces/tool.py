"""Tool interface."""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Abstract tool callable by an agent."""

    name: str

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with keyword arguments."""

