"""Tests for trace-derived runtime latency profiles."""

import json

import pytest

from agentos.events import AgentEvent
from agentos.tracing import RuntimeMetrics, TraceRecord


def event(event_type: str, seconds: float) -> AgentEvent:
    return AgentEvent(
        event_type=event_type,
        run_id="run-1",
        timestamp=f"2026-01-01T00:00:{seconds:06.3f}+00:00",
    )


def test_runtime_metrics_calculate_component_latencies() -> None:
    trace = TraceRecord(
        run_id="run-1",
        events=[
            event("agent.started", 0.0),
            event("planner.started", 0.1),
            event("model.called", 0.2),
            event("model.finished", 0.7),
            event("planner.finished", 0.8),
            event("tool.called", 0.9),
            event("tool.finished", 1.1),
            event("agent.finished", 1.2),
        ],
    )

    metrics = RuntimeMetrics.from_trace(trace)

    assert metrics.run_id == "run-1"
    assert metrics.total_latency == pytest.approx(1.2)
    assert metrics.model_latency == pytest.approx(0.5)
    assert metrics.planner_latency == pytest.approx(0.7)
    assert metrics.tool_latency == pytest.approx(0.2)
    assert metrics.event_count == 8
    assert json.loads(json.dumps(metrics.to_dict()))["run_id"] == "run-1"


def test_runtime_metrics_sum_repeated_calls() -> None:
    trace = TraceRecord(
        run_id="run-1",
        events=[
            event("agent.started", 0.0),
            event("model.called", 0.1),
            event("model.finished", 0.3),
            event("model.called", 0.4),
            event("model.finished", 0.9),
            event("agent.finished", 1.0),
        ],
    )

    assert RuntimeMetrics.from_trace(trace).model_latency == pytest.approx(0.7)


def test_runtime_metrics_accept_started_event_aliases() -> None:
    trace = TraceRecord(
        run_id="run-1",
        events=[
            event("agent.started", 0.0),
            event("model.started", 0.1),
            event("model.finished", 0.4),
            event("tool.started", 0.5),
            event("tool.finished", 0.7),
            event("agent.finished", 0.8),
        ],
    )

    metrics = RuntimeMetrics.from_trace(trace)

    assert metrics.model_latency == pytest.approx(0.3)
    assert metrics.tool_latency == pytest.approx(0.2)
