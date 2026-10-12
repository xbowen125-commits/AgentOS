"""Deterministic model adapter for tests and examples."""

from agentos.interfaces.model import Model


class FakeModel(Model):
    """Return scripted responses in order, then repeat the last response."""

    def __init__(self, responses: list[str]) -> None:
        if not responses:
            raise ValueError("FakeModel requires at least one response")
        self._responses = responses.copy()
        self._index = 0

    async def generate(self, prompt: str) -> str:
        """Return the next deterministic response."""
        del prompt
        index = min(self._index, len(self._responses) - 1)
        response = self._responses[index]
        self._index += 1
        return response
