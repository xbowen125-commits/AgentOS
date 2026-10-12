"""Language model interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class Model(ABC):
    """Abstract language model used by AgentOS."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text for a prompt."""

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Return an async iterator of ordered text chunks when supported."""
        raise NotImplementedError("Streaming is not supported by this model adapter")

        # The unreachable yield makes the default method itself an async generator.
        yield prompt

