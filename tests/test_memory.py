"""Tests for JSON-backed memory."""

import json
from pathlib import Path

from agentos.memory.json_memory import JsonMemory
from agentos.memory.manager import MemoryManager
from agentos.memory.models import MemoryItem


def test_memory_item_can_be_created() -> None:
    item = MemoryItem(
        id="memory-1",
        type="preference",
        content={"language": "Python"},
        created_at="2026-10-12T00:00:00+00:00",
    )

    assert item.content == {"language": "Python"}


def test_json_memory_creates_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "memory.json"

    memory = JsonMemory(path)

    assert path.exists()
    assert memory.all() == []
    assert json.loads(path.read_text(encoding="utf-8")) == []


def test_json_memory_saves_and_reloads_items(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    item = MemoryItem(
        id="memory-1",
        type="event",
        content={"name": "project-created"},
        created_at="2026-10-12T00:00:00+00:00",
    )
    JsonMemory(path).save(item)

    reloaded = JsonMemory(path)

    assert reloaded.load() == [item]


def test_json_memory_queries_by_type(tmp_path: Path) -> None:
    memory = JsonMemory(tmp_path / "memory.json")
    preference = MemoryItem("1", "preference", {"theme": "dark"}, "2026-10-12")
    event = MemoryItem("2", "event", {"name": "login"}, "2026-10-12")
    memory.append(preference)
    memory.append(event)

    assert memory.query(type="preference") == [preference]
    assert memory.query(type="unknown") == []


def test_memory_manager_remembers_and_recalls(tmp_path: Path) -> None:
    manager = MemoryManager(JsonMemory(tmp_path / "memory.json"))

    remembered = manager.remember("preference", {"editor": "vscode"})

    assert manager.recall("preference") == [remembered]
    assert manager.list_memories() == [remembered]
