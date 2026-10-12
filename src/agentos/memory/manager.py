"""High-level memory operations."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agentos.interfaces.memory import MemoryStore
from agentos.memory.models import MemoryItem


class MemoryManager:
    """Create and retrieve structured memories through a JSON store."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def remember(self, type: str, content: dict[str, Any]) -> MemoryItem:
        """Create and persist a new memory item."""
        item = MemoryItem(
            id=str(uuid4()),
            type=type,
            content=content,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save(item)
        return item

    def recall(self, type: str | None = None) -> list[MemoryItem]:
        """Recall memories, optionally filtered by type."""
        return self.store.query(type=type)

    def list_memories(self) -> list[MemoryItem]:
        """List every stored memory item."""
        return self.store.list()
