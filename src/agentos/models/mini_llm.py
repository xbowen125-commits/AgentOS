"""Model adapter for the MiniLLM-Serve HTTP API."""

from dataclasses import dataclass

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

    async def generate(self, prompt: str) -> str:
        """Generate text through MiniLLM-Serve's /generate endpoint."""
        endpoint = f"{self.config.base_url.rstrip('/')}/generate"
        payload = {
            "prompt": prompt,
            "max_tokens": self.config.max_tokens,
        }
        return await self.http_client.post_for_text(
            endpoint,
            payload,
            timeout=self.config.timeout,
        )
