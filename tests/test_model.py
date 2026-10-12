"""Tests for the replaceable model interface and fake adapter."""

import pytest

from agentos.models.fake import FakeModel


@pytest.mark.asyncio
async def test_fake_model_returns_scripted_responses() -> None:
    model = FakeModel(["hello", "world"])

    assert await model.generate("first") == "hello"
    assert await model.generate("second") == "world"


@pytest.mark.asyncio
async def test_fake_model_repeats_last_response_when_exhausted() -> None:
    model = FakeModel(["hello", "world"])

    await model.generate("first")
    await model.generate("second")

    assert await model.generate("third") == "world"
    assert await model.generate("fourth") == "world"


def test_fake_model_requires_a_response() -> None:
    with pytest.raises(ValueError, match="at least one response"):
        FakeModel([])


@pytest.mark.asyncio
async def test_model_stream_is_optional() -> None:
    stream = FakeModel(["response"]).stream("prompt")

    with pytest.raises(NotImplementedError, match="Streaming is not supported"):
        await anext(stream)
