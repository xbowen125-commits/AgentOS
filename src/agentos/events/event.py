"""Serializable runtime event data."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AgentEvent:
    """Describe one observable event in an agent run."""

    event_type: str
    run_id: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str) or not self.event_type:
            raise ValueError("event_type must not be empty")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must not be empty")
        if not isinstance(self.timestamp, str) or not self.timestamp:
            raise ValueError("timestamp must not be empty")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dictionary")
        try:
            json.dumps(asdict(self))
        except (TypeError, ValueError) as error:
            raise TypeError("AgentEvent contains data that is not JSON serializable") from error

    @classmethod
    def create(
        cls,
        event_type: str,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> "AgentEvent":
        """Create an event with a UTC timestamp."""
        return cls(
            event_type=event_type,
            run_id=run_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload={} if payload is None else payload,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation or raise a clear error."""
        data = asdict(self)
        try:
            json.dumps(data)
        except (TypeError, ValueError) as error:
            raise TypeError("AgentEvent contains data that is not JSON serializable") from error
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, run_id: str | None = None) -> "AgentEvent":
        """Build an event from persisted JSON data."""
        event_type = data["event_type"]
        event_run_id = run_id if run_id is not None else data["run_id"]
        timestamp = data["timestamp"]
        payload = data.get("payload", {})
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("Event type must be a non-empty string")
        if not isinstance(event_run_id, str) or not event_run_id:
            raise ValueError("Event run ID must be a non-empty string")
        if not isinstance(timestamp, str) or not timestamp:
            raise ValueError("Event timestamp must be a non-empty string")
        if not isinstance(payload, dict):
            raise TypeError("Event payload must be a JSON object")
        return cls(event_type, event_run_id, timestamp, dict(payload))
