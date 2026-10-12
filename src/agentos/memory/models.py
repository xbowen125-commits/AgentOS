"""Data models stored by the memory runtime."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryItem:
    """A single structured memory record."""

    id: str
    type: str
    content: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Convert the item into JSON-serializable data."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        """Create an item from stored JSON data."""
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            content=dict(data["content"]),
            created_at=str(data["created_at"]),
        )
