"""Latency profiling derived from public runtime traces."""

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from agentos.events import AgentEvent
from agentos.tracing.trace import TraceRecord


@dataclass(frozen=True)
class RuntimeMetrics:
    """Serializable latency profile for one agent run."""

    run_id: str
    total_latency: float
    model_latency: float
    tool_latency: float
    planner_latency: float
    event_count: int

    @classmethod
    def from_trace(cls, trace: TraceRecord) -> "RuntimeMetrics":
        """Calculate total and component latency from paired lifecycle events."""
        total_latency = 0.0
        if len(trace.events) >= 2:
            started_at = _timestamp(trace.events[0])
            finished_at = _timestamp(trace.events[-1])
            total_latency = max(0.0, (finished_at - started_at).total_seconds())
        return cls(
            run_id=trace.run_id,
            total_latency=total_latency,
            model_latency=_component_latency(
                trace.events,
                ("model.called", "model.started"),
                "model.finished",
            ),
            tool_latency=_component_latency(
                trace.events,
                ("tool.called", "tool.started"),
                "tool.finished",
            ),
            planner_latency=_paired_latency(trace.events, "planner.started", "planner.finished"),
            event_count=len(trace.events),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a representation accepted by standard JSON encoders."""
        return asdict(self)


def _timestamp(event: AgentEvent) -> datetime:
    try:
        return datetime.fromisoformat(event.timestamp)
    except ValueError as error:
        raise ValueError(f"Invalid timestamp for event {event.event_type!r}") from error


def _paired_latency(events: list[AgentEvent], started: str, finished: str) -> float:
    starts: deque[datetime] = deque()
    latency = 0.0
    for event in events:
        if event.event_type == started:
            starts.append(_timestamp(event))
        elif event.event_type == finished and starts:
            started_at = starts.popleft()
            latency += max(0.0, (_timestamp(event) - started_at).total_seconds())
    return latency


def _component_latency(
    events: list[AgentEvent],
    start_event_types: tuple[str, ...],
    finished: str,
) -> float:
    started = next(
        (
            event_type
            for event_type in start_event_types
            if any(event.event_type == event_type for event in events)
        ),
        start_event_types[0],
    )
    return _paired_latency(events, started, finished)
