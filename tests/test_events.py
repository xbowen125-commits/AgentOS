"""Tests for runtime events and their failure-isolated bus."""

import json

import pytest

from agentos.events import AgentEvent, EventBus


def test_agent_event_is_json_serializable() -> None:
    event = AgentEvent.create("agent.started", "run-1", {"step": 1})

    assert json.loads(json.dumps(event.to_dict()))["payload"] == {"step": 1}


def test_agent_event_rejects_exception_objects() -> None:
    with pytest.raises(TypeError, match="not JSON serializable"):
        AgentEvent.create("agent.failed", "run-1", {"error": RuntimeError("failed")})


@pytest.mark.asyncio
async def test_event_bus_supports_sync_and_async_handlers() -> None:
    bus = EventBus()
    received: list[str] = []

    def sync_handler(event: AgentEvent) -> None:
        received.append(f"sync:{event.event_type}")

    async def async_handler(event: AgentEvent) -> None:
        received.append(f"async:{event.event_type}")

    bus.subscribe(sync_handler)
    bus.subscribe(async_handler)

    await bus.emit(AgentEvent.create("agent.started", "run-1"))

    assert received == ["sync:agent.started", "async:agent.started"]


@pytest.mark.asyncio
async def test_event_bus_isolates_handler_failures() -> None:
    bus = EventBus()
    received: list[str] = []

    def failing_handler(event: AgentEvent) -> None:
        del event
        raise RuntimeError("handler failed")

    def healthy_handler(event: AgentEvent) -> None:
        received.append(event.event_type)

    bus.subscribe(failing_handler)
    bus.subscribe(healthy_handler)

    await bus.emit(AgentEvent.create("agent.finished", "run-1"))

    assert received == ["agent.finished"]
