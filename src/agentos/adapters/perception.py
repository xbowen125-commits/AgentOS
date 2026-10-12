"""Engine-neutral perception event protocol."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass(frozen=True)
class PerceptionEvent:
    """A structured external interaction event accepted by AgentOS."""

    supported_event_types: ClassVar[frozenset[str]] = frozenset(
        {
            "player.detected",
            "player.wave",
            "player.look",
            "player.speech",
        }
    )

    event_type: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in self.supported_event_types:
            raise ValueError(f"Unsupported perception event type: {self.event_type}")
        if not isinstance(self.timestamp, str) or not self.timestamp:
            raise ValueError("Perception event timestamp must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise TypeError("Perception event payload must be a dictionary")
        try:
            json.dumps(asdict(self))
        except (TypeError, ValueError) as error:
            raise TypeError("Perception event must be JSON serializable") from error

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> "PerceptionEvent":
        """Create an event with a UTC timestamp."""
        return cls(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={} if payload is None else payload,
        )

    @classmethod
    def from_external(cls, data: dict[str, Any]) -> "PerceptionEvent":
        """Parse the compact bridge protocol used by external environments."""
        event_type = data.get("type", data.get("event_type"))
        if not isinstance(event_type, str):
            raise TypeError("External interaction type must be a string")
        timestamp = data.get("timestamp")
        payload = data.get("payload", {})
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()
        if not isinstance(timestamp, str):
            raise TypeError("External interaction timestamp must be a string")
        if not isinstance(payload, dict):
            raise TypeError("External interaction payload must be a dictionary")
        return cls(event_type=event_type, timestamp=timestamp, payload=dict(payload))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible event document."""
        return asdict(self)
