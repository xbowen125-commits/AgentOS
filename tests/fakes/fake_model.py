"""Fake model used by tests."""

from agentos.interfaces.model import Model


class FakeModel(Model):
    """Return a deterministic response without calling a real model."""

    async def generate(self, prompt: str) -> str:
        return "fake response"
