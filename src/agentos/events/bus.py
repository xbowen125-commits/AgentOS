"""Failure-isolated in-process runtime event bus."""

import inspect
from collections.abc import Awaitable, Callable

from agentos.events.event import AgentEvent

EventHandler = Callable[[AgentEvent], None | Awaitable[None]]


class EventBus:
    """Dispatch events to synchronous and asynchronous subscribers."""

    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        """Register a handler for future events."""
        self._handlers.append(handler)

    async def emit(self, event: AgentEvent) -> None:
        """Notify every handler while isolating ordinary handler failures."""
        for handler in tuple(self._handlers):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:  # noqa: BLE001, S112
                continue
