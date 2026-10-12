"""Execution trace data model."""

from dataclasses import dataclass, field

from agentos.events.event import AgentEvent


@dataclass
class TraceRecord:
    """Collect the observable events belonging to one agent run."""

    run_id: str
    events: list[AgentEvent] = field(default_factory=list)

    def append(self, event: AgentEvent) -> None:
        """Add an event after checking that it belongs to this trace."""
        if event.run_id != self.run_id:
            raise ValueError(
                f"Event run ID {event.run_id!r} does not match trace {self.run_id!r}"
            )
        self.events.append(event)
