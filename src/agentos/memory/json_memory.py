"""Versioned JSON adapter for local memory persistence."""

import builtins
import json
import os
import tempfile
import threading
from _thread import LockType
from pathlib import Path
from typing import Any, ClassVar

from agentos.exceptions import (
    MemoryFormatError,
    MemoryItemNotFoundError,
    MemoryStoreError,
    MemoryVersionError,
)
from agentos.interfaces.memory import MemoryStore
from agentos.memory.models import MemoryItem


class JsonMemory(MemoryStore):
    """Persist structured memory items in a versioned JSON document."""

    schema_version = 1
    _path_locks: ClassVar[dict[Path, LockType]] = {}
    _path_locks_guard: ClassVar[LockType] = threading.Lock()

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        self._lock = self._get_path_lock(self.path)
        with self._lock:
            self._ensure_file_unlocked()

    def save(self, item: MemoryItem) -> None:
        """Insert an item or replace the existing item with the same ID."""
        with self._lock:
            items = self._load_unlocked()
            for index, existing in enumerate(items):
                if existing.id == item.id:
                    items[index] = item
                    self._write_unlocked(items)
                    return
            items.append(item)
            self._write_unlocked(items)

    def get(self, item_id: str) -> MemoryItem:
        """Return one memory item by ID."""
        with self._lock:
            for item in self._load_unlocked():
                if item.id == item_id:
                    return item
        raise MemoryItemNotFoundError(f"Memory item not found: {item_id}")

    def list(self) -> builtins.list[MemoryItem]:
        """Return all stored memory items."""
        with self._lock:
            return self._load_unlocked()

    def query(self, type: str | None = None) -> builtins.list[MemoryItem]:
        """Return all items, optionally filtered by memory type."""
        with self._lock:
            items = self._load_unlocked()
        if type is None:
            return items
        return [item for item in items if item.type == type]

    def delete(self, item_id: str) -> None:
        """Delete one memory item by ID."""
        with self._lock:
            items = self._load_unlocked()
            remaining = [item for item in items if item.id != item_id]
            if len(remaining) == len(items):
                raise MemoryItemNotFoundError(f"Memory item not found: {item_id}")
            self._write_unlocked(remaining)

    @classmethod
    def _get_path_lock(cls, path: Path) -> LockType:
        with cls._path_locks_guard:
            lock = cls._path_locks.get(path)
            if lock is None:
                lock = threading.Lock()
                cls._path_locks[path] = lock
            return lock

    def _ensure_file_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_unlocked([])

    def _load_unlocked(self) -> builtins.list[MemoryItem]:
        self._ensure_file_unlocked()
        try:
            with self.path.open(encoding="utf-8") as memory_file:
                document: Any = json.load(memory_file)
        except json.JSONDecodeError as error:
            raise MemoryFormatError(f"Memory file contains invalid JSON: {self.path}") from error
        except OSError as error:
            raise MemoryStoreError(f"Unable to read memory file: {self.path}") from error

        if not isinstance(document, dict):
            raise MemoryFormatError("Memory document must be a JSON object")
        version = document.get("version")
        if version != self.schema_version:
            raise MemoryVersionError(
                f"Unsupported memory schema version: {version!r}; expected {self.schema_version}"
            )
        raw_items = document.get("items")
        if not isinstance(raw_items, list):
            raise MemoryFormatError("Memory document 'items' must be a JSON list")

        items: builtins.list[MemoryItem] = []
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise MemoryFormatError(f"Memory item at index {index} must be a JSON object")
            try:
                items.append(MemoryItem.from_dict(dict(raw_item)))
            except (KeyError, TypeError, ValueError) as error:
                raise MemoryFormatError(f"Invalid memory item at index {index}") from error
        return items

    def _write_unlocked(self, items: builtins.list[MemoryItem]) -> None:
        document = {
            "version": self.schema_version,
            "items": [item.to_dict() for item in items],
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f"{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(document, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except (OSError, TypeError, ValueError) as error:
            raise MemoryStoreError(f"Unable to write memory file: {self.path}") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
