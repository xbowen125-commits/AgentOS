"""JSON-compatible streaming events sharing the runtime event contract."""

from dataclasses import dataclass

from agentos.events import AgentEvent


@dataclass(frozen=True)
class StreamEvent(AgentEvent):
    """Describe a stream lifecycle transition or one visible model text chunk."""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.event_type not in (
            "stream.started", "model.token", "model.completed", "stream.finished"
        ):
            raise ValueError("Unsupported streaming event type")
