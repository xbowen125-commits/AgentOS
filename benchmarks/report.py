"""Markdown reporting for AgentOS benchmark runs."""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from benchmarks.metrics import EvaluationMetrics


class ReportResult(Protocol):
    """Result fields displayed in the failure section."""

    @property
    def case_id(self) -> str: ...

    @property
    def success(self) -> bool: ...

    @property
    def failure_reason(self) -> str | None: ...


def render_markdown_report(
    metrics: EvaluationMetrics,
    results: Sequence[ReportResult],
) -> str:
    """Render aggregate metrics and failures as Markdown."""
    failures = [result for result in results if not result.success]
    failure_lines = (
        [f"- `{result.case_id}`: {result.failure_reason or 'Unknown failure'}" for result in failures]
        if failures
        else ["- None"]
    )
    return "\n".join(
        [
            "# AgentOS Benchmark Report",
            "",
            f"Total Cases: {metrics.total_cases}",
            "",
            f"Successful Cases: {metrics.successful_cases}",
            "",
            f"Failed Cases: {metrics.failed_cases}",
            "",
            f"Success Rate: {metrics.success_rate:.1%}",
            "",
            f"Average Latency: {metrics.average_latency:.4f}s",
            "",
            f"Average Model Calls: {metrics.average_model_calls:.2f}",
            "",
            f"Average Tool Calls: {metrics.average_tool_calls:.2f}",
            "",
            "## Failures",
            "",
            *failure_lines,
            "",
        ]
    )


def write_markdown_report(path: str | Path, report: str) -> None:
    """Write a rendered report to disk."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
