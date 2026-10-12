"""Thread-safe in-memory cache adapter."""

import threading
from typing import Generic

from agentos.cache.cache import Cache, CacheValue


class MemoryCache(Cache[CacheValue], Generic[CacheValue]):
    """Store process-local cache values in a dictionary."""

    def __init__(self) -> None:
        self._values: dict[str, CacheValue] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> CacheValue | None:
        """Return a value without exposing the internal dictionary."""
        with self._lock:
            return self._values.get(key)

    def set(self, key: str, value: CacheValue) -> None:
        """Insert or replace a value."""
        with self._lock:
            self._values[key] = value

    def clear(self) -> None:
        """Remove all values."""
        with self._lock:
            self._values.clear()
