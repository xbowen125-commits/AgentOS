"""HTTP boundary used by model adapters."""

from collections.abc import AsyncGenerator
from typing import Any

import httpx

from agentos.exceptions import MiniLLMConnectionError, MiniLLMResponseError


class HttpClient:
    """Send JSON requests without exposing httpx exceptions to the runtime."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def post_for_text(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> str:
        """POST a JSON payload and return the response's text field."""
        data = await self.post_json_object(url, payload, timeout)
        text = data.get("text")
        if not isinstance(text, str):
            raise MiniLLMResponseError("MiniLLM-Serve response field 'text' must be a string")
        return text

    async def get_json_object(self, url: str, timeout: float) -> dict[str, Any]:
        """GET a JSON object while normalizing transport and response failures."""
        return await self._request_json_object("GET", url, timeout=timeout)

    async def post_json_object(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        """POST a JSON object and return a validated JSON object response."""
        return await self._request_json_object("POST", url, payload=payload, timeout=timeout)

    async def post_sse(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> AsyncGenerator[str, None]:
        """Yield SSE data messages without buffering the complete HTTP response."""
        try:
            async with (
                httpx.AsyncClient(transport=self._transport, timeout=timeout) as client,
                client.stream(
                    "POST", url, json=payload, headers={"Accept": "text/event-stream"}
                ) as response,
            ):
                if not 200 <= response.status_code < 300:
                    raise MiniLLMResponseError(
                        f"MiniLLM-Serve returned HTTP status {response.status_code}"
                    )
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                if content_type.strip().lower() != "text/event-stream":
                    raise MiniLLMResponseError("MiniLLM-Serve response must be text/event-stream")
                response.encoding = "utf-8"
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line == "":
                        if data_lines:
                            yield "\n".join(data_lines)
                            data_lines.clear()
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].removeprefix(" "))
                    # SSE comments and event/id/retry fields carry no token data.
                if data_lines:
                    yield "\n".join(data_lines)
        except httpx.TimeoutException:
            raise MiniLLMConnectionError(f"MiniLLM-Serve stream timed out after {timeout}s") from None
        except httpx.RequestError:
            raise MiniLLMConnectionError("MiniLLM-Serve streaming connection failed") from None

    async def _request_json_object(
        self,
        method: str,
        url: str,
        *,
        timeout: float,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
                response = await client.request(method, url, json=payload)
        except httpx.TimeoutException:
            raise MiniLLMConnectionError(f"MiniLLM-Serve request timed out after {timeout}s") from None
        except httpx.RequestError:
            raise MiniLLMConnectionError("Unable to connect to MiniLLM-Serve") from None

        if not 200 <= response.status_code < 300:
            raise MiniLLMResponseError(
                f"MiniLLM-Serve returned HTTP status {response.status_code}"
            )

        try:
            data: Any = response.json()
        except ValueError:
            raise MiniLLMResponseError("MiniLLM-Serve returned invalid JSON") from None

        if not isinstance(data, dict):
            raise MiniLLMResponseError("MiniLLM-Serve response must be a JSON object")
        return dict(data)
