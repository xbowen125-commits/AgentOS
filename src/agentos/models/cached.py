"""Caching decorator for replaceable model adapters."""

import hashlib
from collections.abc import AsyncIterator

from agentos.cache.cache import Cache
from agentos.events import AgentEvent, EventBus
from agentos.interfaces.model import Model


class CachedModel(Model):
    """Cache generate responses while preserving the backend streaming path."""

    def __init__(
        self,
        backend: Model,
        cache: Cache[str],
        event_bus: EventBus | None = None,
    ) -> None:
        self.backend = backend
        self.cache = cache
        self.event_bus = event_bus

    async def generate(self, prompt: str) -> str:
        """Return a cached response or populate the cache from the backend."""
        key = self._key_for(prompt)
        cached_response = self.cache.get(key)
        if cached_response is not None:
            await self._emit("cache.hit", key)
            return cached_response

        await self._emit("cache.miss", key)
        response = await self.backend.generate(prompt)
        self.cache.set(key, response)
        return response

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Delegate streaming unchanged instead of buffering it into the cache."""
        async for chunk in self.backend.stream(prompt):
            yield chunk

    @staticmethod
    def _key_for(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    async def _emit(self, event_type: str, key: str) -> None:
        if self.event_bus is None or self.event_bus.current_run_id is None:
            return
        await self.event_bus.emit(
            AgentEvent.create(
                event_type,
                self.event_bus.current_run_id,
                {"cache_key": key},
            )
        )
