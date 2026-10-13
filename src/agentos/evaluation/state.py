"""Environment state, independent of core execution history."""

from copy import deepcopy
from typing import Any


class AgentState:
    """A small snapshot-isolated container; not core.AgentState."""

    def __init__(self, initial_state: dict[str, Any] | None = None) -> None:
        self._data = deepcopy(initial_state or {})

    def get(self, key: str, default: Any = None) -> Any:
        return deepcopy(self._data.get(key, default))

    def update(self, values: dict[str, Any]) -> None:
        """Merge top-level keys, copying nested values."""
        self._data.update(deepcopy(values))

    def reset(self, values: dict[str, Any]) -> None:
        """Replace state before a trial, retaining the container identity."""
        self._data = deepcopy(values)

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._data)
