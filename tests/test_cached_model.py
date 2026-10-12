"""Tests for the model response cache decorator."""

from collections.abc import AsyncIterator

import pytest

from agentos.cache import MemoryCache
from agentos.events import AgentEvent, EventBus
from agentos.interfaces.model import Model
from agentos.models.cached import CachedModel


class CountingModel(Model):
    """Record backend calls while returning deterministic content."""

    def __init__(self) -> None:
        self.generate_calls = 0
        self.stream_calls = 0

    async def generate(self, prompt: str) -> str:
        self.generate_calls += 1
        return f"response:{prompt}"

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.stream_calls += 1
        for chunk in ("stream:", prompt):
            yield chunk


@pytest.mark.asyncio
async def test_cached_model_calls_backend_once_and_emits_cache_events() -> None:
    backend = CountingModel()
    event_bus = EventBus()
    events: list[AgentEvent] = []
    event_bus.subscribe(events.append)
    await event_bus.emit(AgentEvent.create("agent.started", "run-1"))
    model = CachedModel(backend, MemoryCache(), event_bus)

    first = await model.generate("hello")
    second = await model.generate("hello")

    assert first == second == "response:hello"
    assert backend.generate_calls == 1
    assert [event.event_type for event in events] == [
        "agent.started",
        "cache.miss",
        "cache.hit",
    ]
    assert {event.run_id for event in events} == {"run-1"}
    assert "hello" not in events[-1].payload["cache_key"]


@pytest.mark.asyncio
async def test_cached_model_preserves_backend_streaming() -> None:
    backend = CountingModel()
    model = CachedModel(backend, MemoryCache())

    chunks = [chunk async for chunk in model.stream("hello")]

    assert chunks == ["stream:", "hello"]
    assert backend.stream_calls == 1
