"""Tests for the in-memory cache adapter."""

from agentos.cache import MemoryCache


def test_memory_cache_set_get_hit_and_miss() -> None:
    cache = MemoryCache[str]()

    assert cache.get("missing") is None
    cache.set("key", "value")

    assert cache.get("key") == "value"


def test_memory_cache_clear_removes_values() -> None:
    cache = MemoryCache[str]()
    cache.set("first", "one")
    cache.set("second", "two")

    cache.clear()

    assert cache.get("first") is None
    assert cache.get("second") is None
