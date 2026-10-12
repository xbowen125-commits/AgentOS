"""Contract tests for the real MiniLLM-Serve validation path."""

import json
from pathlib import Path

import httpx
import pytest

from agentos.exceptions import MiniLLMConnectionError, MiniLLMResponseError
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from examples.real_mini_llm_agent import run_validation
from tests.fakes.fake_mini_llm_server import FakeMiniLLMServer


def build_model(server: FakeMiniLLMServer) -> MiniLLMModel:
    return MiniLLMModel(
        MiniLLMConfig("http://mini-llm.test", timeout=3.0, max_tokens=256),
        HttpClient(transport=server.transport),
    )


@pytest.mark.asyncio
async def test_real_contract_request_and_response_schema() -> None:
    server = FakeMiniLLMServer(response_text='{"type":"final","answer":"56088"}')

    response = await build_model(server).generate("planner prompt")

    assert response == '{"type":"final","answer":"56088"}'
    assert [request.url.path for request in server.requests] == [
        "/health",
        "/v1/chat/completions",
    ]
    payload = json.loads(server.chat_requests[0].content)
    assert payload == {
        "model": "Qwen/Qwen2.5-1.5B-Instruct",
        "messages": [{"role": "user", "content": "planner prompt"}],
        "max_tokens": 256,
        "stream": False,
    }


@pytest.mark.asyncio
async def test_real_contract_timeout_is_normalized() -> None:
    with pytest.raises(MiniLLMConnectionError, match="timed out after 3.0s"):
        await build_model(FakeMiniLLMServer(timeout=True)).generate("prompt")


@pytest.mark.asyncio
async def test_real_contract_http_error_is_normalized() -> None:
    with pytest.raises(MiniLLMResponseError, match="HTTP status 503"):
        await build_model(FakeMiniLLMServer(status_code=503)).generate("prompt")


@pytest.mark.asyncio
async def test_real_contract_rejects_invalid_response_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"model": "Qwen/Qwen2.5-1.5B-Instruct"})
        return httpx.Response(200, json={"choices": []})

    model = MiniLLMModel(
        MiniLLMConfig("http://mini-llm.test"),
        HttpClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(MiniLLMResponseError, match="choices.*non-empty"):
        await model.generate("prompt")


@pytest.mark.asyncio
async def test_real_validation_trace_is_complete_and_sanitized(tmp_path: Path) -> None:
    config_path = tmp_path / "mini_llm.json"
    config_path.write_text(
        json.dumps(
            {"base_url": "http://mini-llm.test", "timeout": 3, "max_tokens": 256}
        ),
        encoding="utf-8",
    )
    server = FakeMiniLLMServer(
        responses=[
            json.dumps(
                {
                    "type": "tool_call",
                    "tool_name": "calculator",
                    "arguments": {"expression": "123*456"},
                }
            ),
            json.dumps({"type": "final", "answer": "56088"}),
        ]
    )

    result = await run_validation(
        config_path=config_path,
        trace_directory=tmp_path / "traces",
        memory_path=tmp_path / "memory.json",
        http_client=HttpClient(transport=server.transport),
    )

    trace_document = json.loads(result.trace_path.read_text(encoding="utf-8"))
    event_types = {event["event_type"] for event in trace_document["events"]}
    assert result.answer == "56088"
    assert result.model_calls == 2
    assert result.tool_calls == 1
    assert {
        "agent.started",
        "planner.decision",
        "model.called",
        "tool.called",
        "agent.completed",
    } <= event_types
    serialized = json.dumps(trace_document, ensure_ascii=False)
    assert "Choose the next agent action" not in serialized
    assert "计算 123*456" not in serialized
