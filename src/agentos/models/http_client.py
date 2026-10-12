"""HTTP boundary used by model adapters."""

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
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
                response = await client.post(url, json=payload)
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
        text = data.get("text")
        if not isinstance(text, str):
            raise MiniLLMResponseError("MiniLLM-Serve response field 'text' must be a string")
        return text
