"""Memory interface."""

from abc import ABC, abstractmethod
from typing import Any


class Memory(ABC):
    """Abstract memory used by an agent."""

    @abstractmethod
    def store(self, data: dict[str, Any]) -> None:
        """Store a memory record."""

    @abstractmethod
    def retrieve(self) -> Any:
        """Retrieve memory data."""

