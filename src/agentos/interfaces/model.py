"""Language model interface."""

from abc import ABC, abstractmethod


class Model(ABC):
    """Abstract language model used by AgentOS."""

    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate text for a prompt."""

