"""Model adapter for the MiniLLM-Serve HTTP API."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agentos.exceptions import MiniLLMResponseError
from agentos.interfaces.model import Model
from agentos.models.http_client import HttpClient


@dataclass(frozen=True)
class MiniLLMConfig:
    """Connection and generation settings for MiniLLM-Serve."""

    base_url: str
    timeout: float = 30.0
    max_tokens: int = 128

    def __post_init__(self) -> None:
        if not self.base_url.strip():
            raise ValueError("base_url must not be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")


class MiniLLMModel(Model):
    """Translate the Model interface into MiniLLM-Serve HTTP requests."""

    def __init__(self, config: MiniLLMConfig, http_client: HttpClient | None = None) -> None:
        self.config = config
        self.http_client = http_client or HttpClient()
        self._model_name: str | None = None

    async def generate(self, prompt: str) -> str:
        """Generate text through MiniLLM-Serve's OpenAI-compatible chat endpoint."""
        model_name = await self._resolve_model_name()
        endpoint = f"{self.config.base_url.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }
        response = await self.http_client.post_json_object(
            endpoint,
            payload,
            timeout=self.config.timeout,
        )
        return self._response_text(response)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Yield ordered chunks from one non-streaming MiniLLM response."""
        response = await self.generate(prompt)
        for chunk in response:
            yield chunk

    async def _resolve_model_name(self) -> str:
        if self._model_name is not None:
            return self._model_name
        endpoint = f"{self.config.base_url.rstrip('/')}/health"
        health = await self.http_client.get_json_object(endpoint, timeout=self.config.timeout)
        model_name = health.get("model")
        if not isinstance(model_name, str) or not model_name:
            raise MiniLLMResponseError("MiniLLM-Serve health field 'model' must be a string")
        self._model_name = model_name
        return model_name

    @staticmethod
    def _response_text(response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise MiniLLMResponseError("MiniLLM-Serve response field 'choices' must be non-empty")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise MiniLLMResponseError("MiniLLM-Serve response choice must contain a message object")
        content = message.get("content")
        if not isinstance(content, str):
            raise MiniLLMResponseError("MiniLLM-Serve response message content must be a string")
        return content
