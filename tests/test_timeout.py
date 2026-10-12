"""Tests for asynchronous runtime timeout control."""

import asyncio

import pytest

from agentos.exceptions import RuntimeTimeoutError
from agentos.runtime import TimeoutController


@pytest.mark.asyncio
async def test_timeout_context_converts_timeout_to_agentos_error() -> None:
    with pytest.raises(RuntimeTimeoutError, match="exceeded timeout"):
        async with TimeoutController(0.01):
            await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_timeout_run_returns_completed_result() -> None:
    async def operation() -> str:
        await asyncio.sleep(0)
        return "complete"

    assert await TimeoutController(1.0).run(operation()) == "complete"


@pytest.mark.asyncio
async def test_timeout_does_not_convert_backend_exception() -> None:
    async def operation() -> None:
        raise ValueError("backend failed")

    with pytest.raises(ValueError, match="backend failed"):
        await TimeoutController(1.0).run(operation())
