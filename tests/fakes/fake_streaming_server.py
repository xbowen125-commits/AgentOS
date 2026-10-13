"""Incrementally delivered MiniLLM-Serve SSE responses for offline tests."""

import json
from collections.abc import AsyncIterator

import httpx


class FakeStreamingBody(httpx.AsyncByteStream):
    def __init__(self, parts: list[bytes], fail_after: int | None = None) -> None:
        self.parts = parts
        self.fail_after = fail_after
        self.closed = False
        self.delivered = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, part in enumerate(self.parts):
            if index == self.fail_after:
                raise httpx.ReadError("simulated disconnect")
            self.delivered += 1
            yield part

    async def aclose(self) -> None:
        self.closed = True


class FakeStreamingServer:
    """Supply role, content, completion, and DONE frames in fragmented bytes."""

    def __init__(
        self,
        tokens: tuple[str, ...] = ("你", "好", "56088"),
        *,
        frames: list[str] | None = None,
        fragment_size: int = 3,
        status_code: int = 200,
        content_type: str = "text/event-stream",
        fail_after: int | None = None,
    ) -> None:
        if frames is None:
            frames = [self.chunk({"role": "assistant"})]
            frames.extend(self.chunk({"content": token}) for token in tokens)
            frames.extend([self.chunk({}, "stop"), "data: [DONE]\n\n"])
        parts: list[bytes] = []
        for frame in frames:
            data = frame.encode("utf-8")
            size = fragment_size or len(data)
            parts.extend(data[index:index + size] for index in range(0, len(data), size))
        self.body = FakeStreamingBody(parts, fail_after)
        self.status_code = status_code
        self.content_type = content_type
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.handle)

    @staticmethod
    def chunk(delta: dict, finish_reason: str | None = None) -> str:
        document = {"choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
        return f"data: {json.dumps(document, ensure_ascii=False)}\n\n"

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET" and request.url.path == "/health":
            return httpx.Response(200, json={"model": "Qwen/Qwen2.5-1.5B-Instruct"})
        if request.method == "POST" and request.url.path == "/v1/chat/completions":
            return httpx.Response(
                self.status_code,
                headers={"Content-Type": self.content_type},
                stream=self.body,
            )
        return httpx.Response(404)
