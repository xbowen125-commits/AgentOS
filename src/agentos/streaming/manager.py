"""Stream text through a Model interface and emit failure-isolated events."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from agentos.events import EventBus
from agentos.interfaces.model import Model
from agentos.streaming.stream_event import StreamEvent


class StreamingManager:
    """Coordinate token delivery without modifying Agent execution or decisions."""

    def __init__(self, model: Model, event_bus: EventBus | None = None) -> None:
        self.model = model
        self.event_bus = event_bus

    async def stream(self, prompt: str, run_id: str | None = None) -> AsyncGenerator[str, None]:
        """Yield ordered text chunks; completion means full stream consumption.

        Consumers stopping early should close this iterator with contextlib.aclosing.
        Token events contain visible output; avoid attaching persistent trace handlers
        when that output may contain private data.
        """
        resolved_run_id = str(uuid4()) if run_id is None else run_id
        if not resolved_run_id:
            raise ValueError("run_id must not be empty")
        chunk_count = 0
        status = "cancelled"
        error_type: str | None = None
        await self._emit("stream.started", resolved_run_id, {})
        try:
            chunks = self.model.stream(prompt)
            try:
                async for token in chunks:
                    await self._emit(
                        "model.token", resolved_run_id, {"token": token, "index": chunk_count}
                    )
                    chunk_count += 1
                    yield token
            finally:
                close = getattr(chunks, "aclose", None)
                if close is not None:
                    await close()
            status = "completed"
            await self._emit("model.completed", resolved_run_id, {"chunk_count": chunk_count})
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except Exception as error:
            status = "failed"
            error_type = type(error).__name__
            raise
        finally:
            await self._emit(
                "stream.finished",
                resolved_run_id,
                {"status": status, "chunk_count": chunk_count, "error_type": error_type},
            )

    async def _emit(self, event_type: str, run_id: str, payload: dict[str, Any]) -> None:
        if self.event_bus is None:
            return
        try:
            await self.event_bus.emit(StreamEvent.create(event_type, run_id, payload))
        except Exception:  # noqa: BLE001
            return
