"""Python 3.10-compatible asynchronous timeout control."""

import asyncio
from asyncio import TimerHandle
from collections.abc import Awaitable
from types import TracebackType
from typing import Literal, TypeVar

from agentos.exceptions import RuntimeTimeoutError

Result = TypeVar("Result")


class TimeoutController:
    """Bound one asynchronous operation with an explicit AgentOS timeout error."""

    def __init__(self, seconds: float) -> None:
        if seconds <= 0:
            raise ValueError("Timeout must be greater than zero")
        self.seconds = seconds
        self._task: asyncio.Task[object] | None = None
        self._timer: TimerHandle | None = None
        self._timed_out = False

    async def __aenter__(self) -> "TimeoutController":  # noqa: PYI034
        if self._task is not None:
            raise RuntimeError("TimeoutController cannot be entered more than once concurrently")
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("TimeoutController requires a running asyncio task")
        self._task = task
        self._timed_out = False
        loop = asyncio.get_running_loop()
        self._timer = loop.call_later(self.seconds, self._cancel_for_timeout)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_value, traceback
        if self._timer is not None:
            self._timer.cancel()
        timed_out = self._timed_out
        self._task = None
        self._timer = None
        self._timed_out = False
        if timed_out and exc_type is asyncio.CancelledError:
            raise RuntimeTimeoutError(
                f"Asynchronous operation exceeded timeout of {self.seconds}s"
            ) from None
        return False

    async def run(self, awaitable: Awaitable[Result]) -> Result:
        """Execute an awaitable within this timeout context."""
        async with self:
            return await awaitable

    def _cancel_for_timeout(self) -> None:
        if self._task is not None and not self._task.done():
            self._timed_out = True
            self._task.cancel()
