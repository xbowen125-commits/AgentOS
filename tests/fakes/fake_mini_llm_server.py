"""In-memory MiniLLM-Serve API used by adapter tests."""

import httpx


class FakeMiniLLMServer:
    """Provide the MiniLLM-Serve health and chat contracts through MockTransport."""

    def __init__(
        self,
        response_text: str = '{"type":"final","answer":"hello"}',
        *,
        responses: list[str] | None = None,
        status_code: int = 200,
        raw_body: str | None = None,
        timeout: bool = False,
        connection_error: bool = False,
        model_name: str = "Qwen/Qwen2.5-1.5B-Instruct",
    ) -> None:
        self.response_text = response_text
        self.responses = responses.copy() if responses is not None else None
        self.status_code = status_code
        self.raw_body = raw_body
        self.timeout = timeout
        self.connection_error = connection_error
        self.model_name = model_name
        self.requests: list[httpx.Request] = []
        self.chat_requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle_request)

    def _handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.timeout:
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if self.connection_error:
            raise httpx.ConnectError("simulated connection failure", request=request)
        if request.method == "GET" and request.url.path == "/health":
            return httpx.Response(
                200,
                json={"status": "ok", "model": self.model_name, "loaded": True},
            )
        if request.method != "POST" or request.url.path != "/v1/chat/completions":
            return httpx.Response(404, json={"error": {"message": "not found"}})

        self.chat_requests.append(request)
        if self.raw_body is not None:
            return httpx.Response(self.status_code, text=self.raw_body)
        response_text = self.response_text
        if self.responses:
            response_index = min(len(self.chat_requests) - 1, len(self.responses) - 1)
            response_text = self.responses[response_index]
        return httpx.Response(
            self.status_code,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": self.model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": response_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
