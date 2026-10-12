"""Tests for performance aggregation and Markdown reporting."""

import json

import pytest

from agentos.events import AgentEvent
from agentos.tracing import TraceRecord
from benchmarks.performance import PerformanceMetrics, render_performance_report


def make_trace(run_id: str, latency: float, cache_event: str) -> TraceRecord:
    return TraceRecord(
        run_id=run_id,
        events=[
            AgentEvent("agent.started", run_id, "2026-01-01T00:00:00+00:00"),
            AgentEvent("model.called", run_id, "2026-01-01T00:00:00.100000+00:00"),
            AgentEvent(cache_event, run_id, "2026-01-01T00:00:00.200000+00:00"),
            AgentEvent("model.finished", run_id, "2026-01-01T00:00:00.300000+00:00"),
            AgentEvent("tool.called", run_id, "2026-01-01T00:00:00.400000+00:00"),
            AgentEvent("tool.finished", run_id, "2026-01-01T00:00:00.500000+00:00"),
            AgentEvent(
                "agent.finished",
                run_id,
                f"2026-01-01T00:00:{latency:06.3f}+00:00",
            ),
        ],
    )


def test_performance_metrics_and_report() -> None:
    traces = [
        make_trace("run-1", 1.0, "cache.miss"),
        make_trace("run-2", 2.0, "cache.hit"),
        make_trace("run-3", 3.0, "cache.hit"),
    ]

    metrics = PerformanceMetrics.from_traces(traces)
    report = render_performance_report(metrics)

    assert metrics.average_latency == pytest.approx(2.0)
    assert metrics.p95_latency == pytest.approx(3.0)
    assert metrics.model_calls == 3
    assert metrics.tool_calls == 3
    assert metrics.cache_hit_rate == pytest.approx(2 / 3)
    assert json.loads(json.dumps(metrics.to_dict()))["run_count"] == 3
    assert report.startswith("# AgentOS Performance Report")
    assert "P95 Latency: 3.0000s" in report
    assert "Cache Hit Rate: 66.7%" in report
