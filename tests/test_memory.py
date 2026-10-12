"""Tests for the versioned JSON memory adapter."""

import builtins
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentos.exceptions import MemoryFormatError, MemoryItemNotFoundError, MemoryVersionError
from agentos.interfaces.memory import MemoryStore
from agentos.memory.json_memory import JsonMemory
from agentos.memory.manager import MemoryManager
from agentos.memory.models import MemoryItem


def make_item(item_id: str, type: str = "event") -> MemoryItem:
    return MemoryItem(
        id=item_id,
        type=type,
        content={"value": item_id},
        created_at="2026-10-12T00:00:00+00:00",
    )


class InMemoryStore(MemoryStore):
    """MemoryStore adapter used to prove the manager is storage-independent."""

    def __init__(self) -> None:
        self.items: dict[str, MemoryItem] = {}

    def save(self, item: MemoryItem) -> None:
        self.items[item.id] = item

    def get(self, item_id: str) -> MemoryItem:
        return self.items[item_id]

    def list(self) -> builtins.list[MemoryItem]:
        return builtins.list(self.items.values())

    def query(self, type: str | None = None) -> builtins.list[MemoryItem]:
        if type is None:
            return self.list()
        return [item for item in self.items.values() if item.type == type]

    def delete(self, item_id: str) -> None:
        del self.items[item_id]


def test_memory_item_can_be_created() -> None:
    item = make_item("memory-1", type="preference")

    assert item.content == {"value": "memory-1"}


def test_json_memory_creates_versioned_document(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "memory.json"

    memory = JsonMemory(path)

    assert path.exists()
    assert memory.list() == []
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1, "items": []}


def test_json_memory_saves_gets_and_lists_items(tmp_path: Path) -> None:
    memory = JsonMemory(tmp_path / "memory.json")
    item = make_item("memory-1")

    memory.save(item)

    assert memory.get("memory-1") == item
    assert memory.list() == [item]


def test_json_memory_updates_existing_id(tmp_path: Path) -> None:
    memory = JsonMemory(tmp_path / "memory.json")
    original = make_item("memory-1")
    updated = MemoryItem(
        id="memory-1",
        type="preference",
        content={"theme": "dark"},
        created_at=original.created_at,
    )

    memory.save(original)
    memory.save(updated)

    assert memory.list() == [updated]


def test_json_memory_queries_by_type(tmp_path: Path) -> None:
    memory = JsonMemory(tmp_path / "memory.json")
    preference = make_item("1", type="preference")
    event = make_item("2", type="event")
    memory.save(preference)
    memory.save(event)

    assert memory.query(type="preference") == [preference]
    assert memory.query(type="unknown") == []


def test_json_memory_deletes_by_id(tmp_path: Path) -> None:
    memory = JsonMemory(tmp_path / "memory.json")
    memory.save(make_item("memory-1"))

    memory.delete("memory-1")

    assert memory.list() == []
    with pytest.raises(MemoryItemNotFoundError, match="memory-1"):
        memory.get("memory-1")


def test_json_memory_rejects_unsupported_version(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    path.write_text('{"version": 2, "items": []}', encoding="utf-8")
    memory = JsonMemory(path)

    with pytest.raises(MemoryVersionError, match="version"):
        memory.list()


def test_json_memory_reports_corrupted_json(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    path.write_text("{not-json", encoding="utf-8")
    memory = JsonMemory(path)

    with pytest.raises(MemoryFormatError, match="invalid JSON"):
        memory.list()


def test_json_memory_serializes_threaded_writes(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    first_store = JsonMemory(path)
    second_store = JsonMemory(path)
    items = [make_item(str(index)) for index in range(20)]

    operations = [
        (first_store if index % 2 == 0 else second_store, item)
        for index, item in enumerate(items)
    ]

    def save(operation: tuple[JsonMemory, MemoryItem]) -> None:
        store, item = operation
        store.save(item)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(save, operations))

    assert {item.id for item in first_store.list()} == {item.id for item in items}
    assert list(tmp_path.glob("memory.json.*.tmp")) == []


def test_memory_manager_depends_on_store_port() -> None:
    manager = MemoryManager(InMemoryStore())

    remembered = manager.remember("preference", {"editor": "vscode"})

    assert manager.recall("preference") == [remembered]
    assert manager.list_memories() == [remembered]
