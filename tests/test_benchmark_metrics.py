"""Tests for benchmark aggregation and trace analysis."""

import json
from dataclasses import dataclass

import pytest

from agentos.events import AgentEvent
from agentos.tracing import TraceRecord
from benchmarks.evaluator import TraceAnalyzer
from benchmarks.metrics import EvaluationMetrics


@dataclass(frozen=True)
class MeasuredCase:
    success: bool
    latency: float
    model_calls: int
    tool_calls: int


def test_metrics_calculate_success_rate_and_averages() -> None:
    results = [
        MeasuredCase(True, 1.0, 2, 1),
        MeasuredCase(True, 2.0, 3, 2),
        MeasuredCase(False, 3.0, 1, 0),
    ]

    metrics = EvaluationMetrics.from_results(results)

    assert metrics.total_cases == 3
    assert metrics.successful_cases == 2
    assert metrics.failed_cases == 1
    assert metrics.success_rate == pytest.approx(2 / 3)
    assert metrics.average_latency == pytest.approx(2.0)
    assert metrics.average_model_calls == pytest.approx(2.0)
    assert metrics.average_tool_calls == pytest.approx(1.0)
    assert json.loads(json.dumps(metrics.to_dict()))["total_cases"] == 3


def test_trace_analyzer_calculates_latency_and_call_counts() -> None:
    trace = TraceRecord(
        run_id="run-1",
        events=[
            AgentEvent("agent.started", "run-1", "2026-01-01T00:00:00+00:00"),
            AgentEvent("model.called", "run-1", "2026-01-01T00:00:00.250000+00:00"),
            AgentEvent("tool.called", "run-1", "2026-01-01T00:00:00.500000+00:00"),
            AgentEvent("model.called", "run-1", "2026-01-01T00:00:00.750000+00:00"),
            AgentEvent("agent.finished", "run-1", "2026-01-01T00:00:01+00:00"),
        ],
    )

    analysis = TraceAnalyzer.analyze(trace)

    assert analysis.latency == pytest.approx(1.0)
    assert analysis.model_calls == 2
    assert analysis.tool_calls == 1
    assert analysis.finished is True
    assert analysis.failed is False
