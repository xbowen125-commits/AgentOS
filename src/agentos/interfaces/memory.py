"""Storage port for structured AgentOS memories."""

from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentos.memory.models import MemoryItem


class MemoryStore(ABC):
    """Persistence-independent interface for memory items."""

    @abstractmethod
    def save(self, item: MemoryItem) -> None:
        """Insert a new item or update an existing item by ID."""

    @abstractmethod
    def get(self, item_id: str) -> MemoryItem:
        """Return one item by ID."""

    @abstractmethod
    def list(self) -> builtins.list[MemoryItem]:
        """Return every stored item."""

    @abstractmethod
    def query(self, type: str | None = None) -> builtins.list[MemoryItem]:
        """Return items, optionally filtered by type."""

    @abstractmethod
    def delete(self, item_id: str) -> None:
        """Delete one item by ID."""

