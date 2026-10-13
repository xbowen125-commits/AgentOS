"""Tests for the model streaming contract."""

import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.events import AgentEvent, EventBus
from agentos.exceptions import MiniLLMConnectionError, MiniLLMResponseError
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.tool_prompt import CALCULATOR_DESCRIPTION
from agentos.streaming import StreamingManager
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from examples.real_mini_llm_stream import StreamingPlannerModel
from tests.fakes.fake_streaming_server import FakeStreamingBody, FakeStreamingServer


def build_model(server: FakeStreamingServer) -> MiniLLMModel:
    return MiniLLMModel(
        MiniLLMConfig("http://mini-llm.test", max_tokens=256),
        HttpClient(transport=server.transport),
    )


@pytest.mark.asyncio
async def test_fake_model_stream_preserves_chunk_order() -> None:
    chunks = [chunk async for chunk in FakeModel(["hello"]).stream("prompt")]

    assert chunks == ["h", "e", "l", "l", "o"]


@pytest.mark.asyncio
async def test_native_sse_preserves_order_unicode_and_request_schema() -> None:
    server = FakeStreamingServer()
    model = build_model(server)

    chunks = [chunk async for chunk in model.stream("prompt")]

    assert chunks == ["你", "好", "56088"]
    assert len(server.requests) == 2
    assert server.requests[1].headers["accept"] == "text/event-stream"
    assert json.loads(server.requests[1].content) == {
        "model": "Qwen/Qwen2.5-1.5B-Instruct",
        "messages": [{"role": "user", "content": "prompt"}],
        "max_tokens": 256,
        "stream": True,
    }
    assert server.body.closed


@pytest.mark.asyncio
async def test_manager_emits_ordered_lifecycle_and_token_events() -> None:
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    manager = StreamingManager(build_model(FakeStreamingServer()), bus)
    tokens = [token async for token in manager.stream("prompt", run_id="run-stream")]
    assert tokens == ["你", "好", "56088"]
    assert [event.event_type for event in events] == [
        "stream.started", "model.token", "model.token", "model.token",
        "model.completed", "stream.finished",
    ]
    assert [event.payload["token"] for event in events if event.event_type == "model.token"] == tokens
    assert [event.payload["index"] for event in events if event.event_type == "model.token"] == [0, 1, 2]
    assert all(event.run_id == "run-stream" for event in events)
    assert events[-1].payload == {"status": "completed", "chunk_count": 3, "error_type": None}
    assert "prompt" not in json.dumps([event.to_dict() for event in events])


@pytest.mark.asyncio
async def test_disconnect_preserves_delivered_token_but_does_not_complete() -> None:
    server = FakeStreamingServer(fragment_size=0, fail_after=2)
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    manager = StreamingManager(build_model(server), bus)
    tokens: list[str] = []
    with pytest.raises(MiniLLMConnectionError, match="streaming connection failed"):
        async for token in manager.stream("prompt"):
            tokens.append(token)
    assert tokens == ["你"]
    assert server.body.closed
    assert not any(event.event_type == "model.completed" for event in events)
    assert events[-1].event_type == "stream.finished"
    assert events[-1].payload["status"] == "failed"
    assert events[-1].payload["error_type"] == "MiniLLMConnectionError"


@pytest.mark.asyncio
@pytest.mark.parametrize("frames", [
    ["data: not-json\n\n"],
    ['data: {"error":{"message":"private failure"}}\n\n', "data: [DONE]\n\n"],
    [FakeStreamingServer.chunk({"content": "partial"})],
    [FakeStreamingServer.chunk({}, "stop")],
    ["data: [DONE]\n\n"],
    ['data: {"choices":[]}\n\n'],
    [FakeStreamingServer.chunk({"content": 123})],
])
async def test_invalid_or_incomplete_sse_raises_response_error(frames: list[str]) -> None:
    server = FakeStreamingServer(frames=frames)
    with pytest.raises(MiniLLMResponseError):
        _ = [token async for token in build_model(server).stream("prompt")]
    assert server.body.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("settings", [{"status_code": 503}, {"content_type": "application/json"}])
async def test_stream_status_and_content_type_validation(settings: dict) -> None:
    server = FakeStreamingServer(**settings)
    with pytest.raises(MiniLLMResponseError):
        _ = [token async for token in build_model(server).stream("prompt")]
    assert server.body.closed


@pytest.mark.asyncio
async def test_sse_comments_multiline_data_and_crlf() -> None:
    frames = [
        (
            ': keepalive\r\nevent: message\r\nid: 1\r\n'
            'data: {"choices": [\r\ndata: {"delta": {"content":"hello"}}]}\r\n\r\n'
        ),
        FakeStreamingServer.chunk({}, "stop"),
        "data: [DONE]\n\n",
    ]
    assert [token async for token in build_model(FakeStreamingServer(frames=frames)).stream("p")] == [
        "hello"
    ]


@pytest.mark.asyncio
async def test_early_close_is_incremental_and_closes_http_stream() -> None:
    server = FakeStreamingServer(fragment_size=0)
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    async with aclosing(StreamingManager(build_model(server), bus).stream("prompt")) as stream:
        assert await anext(stream) == "你"
        assert server.body.delivered == 2
    assert server.body.closed
    assert events[-1].payload["status"] == "cancelled"
    assert not any(event.event_type == "model.completed" for event in events)


@pytest.mark.asyncio
async def test_failing_event_handler_does_not_interrupt_stream() -> None:
    def broken(event: AgentEvent) -> None:
        raise RuntimeError("handler failure")

    bus = EventBus()
    bus.subscribe(broken)
    tokens = [token async for token in StreamingManager(FakeModel(["ok"]), bus).stream("prompt")]
    assert tokens == ["o", "k"]


@pytest.mark.asyncio
async def test_timeout_during_stream_is_normalized_and_connection_is_closed() -> None:
    class TimeoutBody(FakeStreamingBody):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b': keepalive\n\n'
            raise httpx.ReadTimeout("simulated timeout")

    server = FakeStreamingServer()
    server.body = TimeoutBody([])
    with pytest.raises(MiniLLMConnectionError, match="stream timed out"):
        _ = [token async for token in build_model(server).stream("prompt")]
    assert server.body.closed


@pytest.mark.asyncio
async def test_native_streamed_decisions_complete_agent_tool_loop(tmp_path: Path) -> None:
    first = FakeStreamingServer(tokens=(
        '{"type":"tool_call","tool_name":"calculator",',
        '"arguments":{"expression":"123*456"}}',
    ))
    second = FakeStreamingServer(tokens=('{"type":"final",', '"answer":"56088"}'))
    responses = iter((first, second))

    def handler(request: httpx.Request) -> httpx.Response:
        server = first if request.method == "GET" else next(responses)
        return server.handle(request)

    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    backend = MiniLLMModel(
        MiniLLMConfig("http://mini-llm.test"),
        HttpClient(transport=httpx.MockTransport(handler)),
    )
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    agent = Agent(
        planner=ModelPlanner(
            StreamingPlannerModel(backend, bus), [CALCULATOR_DESCRIPTION],
            event_bus=bus, required_tool="calculator",
        ),
        tool_executor=ToolExecutor(registry),
        memory=JsonMemory(tmp_path / "memory.json"),
        event_bus=bus,
    )
    state = await agent.run("计算 123*456")
    assert state.finished
    assert state.history == [
        ToolCallDecision("calculator", {"expression": "123*456"}),
        Observation(success=True, result="56088"),
        FinalAnswerDecision("56088"),
    ]
    assert all(json.loads(request.content)["stream"] is True for request in first.requests[1:])
    assert all(json.loads(request.content)["stream"] is True for request in second.requests)
    assert sum(event.event_type == "model.completed" for event in events) == 2
    assert sum(event.event_type == "stream.finished" for event in events) == 2
    assert sum(event.event_type == "model.token" for event in events) == 4
    assert first.body.closed and second.body.closed
