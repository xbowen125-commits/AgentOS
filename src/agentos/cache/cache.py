"""Cache port used by AgentOS adapters."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

CacheValue = TypeVar("CacheValue")


class Cache(ABC, Generic[CacheValue]):
    """Minimal synchronous key-value cache interface."""

    @abstractmethod
    def get(self, key: str) -> CacheValue | None:
        """Return a cached value, or None when the key is absent."""

    @abstractmethod
    def set(self, key: str, value: CacheValue) -> None:
        """Store a value under a key."""

    @abstractmethod
    def clear(self) -> None:
        """Remove every cached value."""
