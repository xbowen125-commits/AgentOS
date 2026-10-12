"""Tests for the model streaming contract."""

import pytest

from agentos.models.fake import FakeModel
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from tests.fakes.fake_mini_llm_server import FakeMiniLLMServer


@pytest.mark.asyncio
async def test_fake_model_stream_preserves_chunk_order() -> None:
    chunks = [chunk async for chunk in FakeModel(["hello"]).stream("prompt")]

    assert chunks == ["h", "e", "l", "l", "o"]


@pytest.mark.asyncio
async def test_mini_llm_stream_reuses_generate_and_preserves_order() -> None:
    server = FakeMiniLLMServer(response_text="hello")
    model = MiniLLMModel(
        MiniLLMConfig(base_url="http://mini-llm.test"),
        HttpClient(transport=server.transport),
    )

    chunks = [chunk async for chunk in model.stream("prompt")]

    assert chunks == ["h", "e", "l", "l", "o"]
    assert len(server.requests) == 1
