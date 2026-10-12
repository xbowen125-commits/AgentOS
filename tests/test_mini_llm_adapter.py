"""Tests for the MiniLLM-Serve model adapter."""

import json

import pytest

from agentos.exceptions import MiniLLMConnectionError, MiniLLMResponseError
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from tests.fakes.fake_mini_llm_server import FakeMiniLLMServer


def build_model(server: FakeMiniLLMServer) -> MiniLLMModel:
    config = MiniLLMConfig(
        base_url="http://mini-llm.test",
        timeout=5.0,
        max_tokens=128,
    )
    return MiniLLMModel(config, HttpClient(transport=server.transport))


@pytest.mark.asyncio
async def test_generate_returns_response_text() -> None:
    server = FakeMiniLLMServer(response_text="response text")
    model = build_model(server)

    result = await model.generate("hello")

    assert result == "response text"
    assert len(server.requests) == 1
    request = server.requests[0]
    assert request.url == "http://mini-llm.test/generate"
    assert json.loads(request.content) == {"prompt": "hello", "max_tokens": 128}


@pytest.mark.asyncio
async def test_server_error_returns_response_error() -> None:
    model = build_model(FakeMiniLLMServer(status_code=500))

    with pytest.raises(MiniLLMResponseError, match="HTTP status 500"):
        await model.generate("hello")


@pytest.mark.asyncio
async def test_timeout_returns_connection_error() -> None:
    model = build_model(FakeMiniLLMServer(timeout=True))

    with pytest.raises(MiniLLMConnectionError, match="timed out"):
        await model.generate("hello")


@pytest.mark.asyncio
async def test_unreachable_server_returns_connection_error() -> None:
    model = build_model(FakeMiniLLMServer(connection_error=True))

    with pytest.raises(MiniLLMConnectionError, match="Unable to connect"):
        await model.generate("hello")


@pytest.mark.asyncio
async def test_invalid_json_returns_response_error() -> None:
    model = build_model(FakeMiniLLMServer(raw_body="not-json"))

    with pytest.raises(MiniLLMResponseError, match="invalid JSON"):
        await model.generate("hello")
