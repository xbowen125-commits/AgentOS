"""JSON-backed local memory storage."""

import json
from pathlib import Path
from typing import Any

from agentos.interfaces.memory import Memory
from agentos.memory.models import MemoryItem


class JsonMemory(Memory):
    """Persist structured memory items in a readable JSON file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._ensure_file()

    def save(self, item: MemoryItem) -> None:
        """Insert an item or replace the existing item with the same ID."""
        items = self.load()
        for index, existing in enumerate(items):
            if existing.id == item.id:
                items[index] = item
                self._write(items)
                return
        items.append(item)
        self._write(items)

    def load(self) -> list[MemoryItem]:
        """Load all memory items from disk."""
        with self.path.open(encoding="utf-8") as memory_file:
            data: Any = json.load(memory_file)

        if not isinstance(data, list):
            raise TypeError("Memory file must contain a JSON list")
        return [MemoryItem.from_dict(item) for item in data]

    def append(self, item: MemoryItem) -> None:
        """Append an item to the memory file."""
        items = self.load()
        items.append(item)
        self._write(items)

    def all(self) -> list[MemoryItem]:
        """Return all stored memory items."""
        return self.load()

    def query(self, type: str | None = None) -> list[MemoryItem]:
        """Return all items, optionally filtered by memory type."""
        items = self.load()
        if type is None:
            return items
        return [item for item in items if item.type == type]

    def store(self, data: dict[str, Any]) -> None:
        """Store dictionary data through the common Memory interface."""
        self.append(MemoryItem.from_dict(data))

    def retrieve(self) -> list[dict[str, Any]]:
        """Retrieve dictionary data through the common Memory interface."""
        return [item.to_dict() for item in self.load()]

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def _write(self, items: list[MemoryItem]) -> None:
        serialized = [item.to_dict() for item in items]
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
