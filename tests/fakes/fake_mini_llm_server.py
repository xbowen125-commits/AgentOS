"""In-memory MiniLLM-Serve API used by adapter tests."""

import httpx


class FakeMiniLLMServer:
    """Provide a configurable /generate endpoint through MockTransport."""

    def __init__(
        self,
        response_text: str = '{"type":"final","answer":"hello"}',
        *,
        responses: list[str] | None = None,
        status_code: int = 200,
        raw_body: str | None = None,
        timeout: bool = False,
        connection_error: bool = False,
    ) -> None:
        self.response_text = response_text
        self.responses = responses.copy() if responses is not None else None
        self.status_code = status_code
        self.raw_body = raw_body
        self.timeout = timeout
        self.connection_error = connection_error
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle_request)

    def _handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.timeout:
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if self.connection_error:
            raise httpx.ConnectError("simulated connection failure", request=request)
        if self.raw_body is not None:
            return httpx.Response(self.status_code, text=self.raw_body)
        response_text = self.response_text
        if self.responses:
            response_index = min(len(self.requests) - 1, len(self.responses) - 1)
            response_text = self.responses[response_index]
        return httpx.Response(self.status_code, json={"text": response_text})
