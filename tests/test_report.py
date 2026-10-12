"""Tests for benchmark Markdown reports."""

from benchmarks.evaluator import BenchmarkResult
from benchmarks.metrics import EvaluationMetrics
from benchmarks.report import render_markdown_report


def test_markdown_report_contains_metrics_and_failures() -> None:
    results = (
        BenchmarkResult("calc_001", True, "2", "2", 1.0, 2, 1),
        BenchmarkResult("calc_002", False, "3", "4", 2.0, 2, 1, "Answer mismatch"),
    )
    metrics = EvaluationMetrics.from_results(results)

    report = render_markdown_report(metrics, results)

    assert report.startswith("# AgentOS Benchmark Report")
    assert "Total Cases: 2" in report
    assert "Success Rate: 50.0%" in report
    assert "Average Latency: 1.5000s" in report
    assert "Average Model Calls: 2.00" in report
    assert "Average Tool Calls: 1.00" in report
    assert "`calc_002`: Answer mismatch" in report
