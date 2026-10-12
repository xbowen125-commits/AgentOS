"""Replaceable cache interfaces and local adapters."""

from agentos.cache.cache import Cache
from agentos.cache.memory_cache import MemoryCache

__all__ = ["Cache", "MemoryCache"]
