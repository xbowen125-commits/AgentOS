"""Language model interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class Model(ABC):
    """Abstract language model used by AgentOS."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text for a prompt."""

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream text chunks when implemented by a model adapter."""
        raise NotImplementedError("Streaming is not supported by this model adapter")

        # This unreachable yield keeps the contract an async iterator for subclasses.
        yield prompt

