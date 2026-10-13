"""Markdown evaluation reports without raw prompts or answer content."""

from collections.abc import Sequence
from pathlib import Path

from agentos.evaluation.evaluator import EvaluationResult
from agentos.evaluation.metrics import EvaluationMetrics


def _rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def _status(value: bool | None) -> str:
    return "N/A" if value is None else ("passed" if value else "failed")


def _cell(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown_report(results: Sequence[EvaluationResult]) -> str:
    metrics = EvaluationMetrics.from_results(results)
    lines = [
        "# AgentOS Evaluation Report", "",
        f"Runs: {metrics.total_runs}", "",
        "| Metric | Value |", "| --- | ---: |",
        f"| Task Success Rate | {_rate(metrics.task_success_rate)} |",
        f"| Tool Selection Accuracy | {_rate(metrics.tool_selection_accuracy)} |",
        f"| Workflow Completion Rate | {_rate(metrics.workflow_completion_rate)} |",
        f"| Average Latency | {metrics.average_latency:.4f}s |",
        f"| Retry Rate | {_rate(metrics.retry_rate)} |",
        f"| Validation Failure Rate | {_rate(metrics.validation_failure_rate)} |",
        "",
        (
            f"Coverage: tasks={metrics.assessed_tasks}/{metrics.total_runs}; "
            f"tool sequences={metrics.assessed_tool_runs}/{metrics.total_runs}; "
            f"workflows={metrics.workflow_runs}/{metrics.total_runs}."
        ),
        "",
        (
            "N/A means unobserved or inapplicable. Retry and validation failure rates are run-level; "
            "recovered validation failures remain counted. Tool accuracy counts ordered matching "
            "positions over max(actual, expected) sequence length, aggregated across assessed runs."
        ),
        "", "## Run Results", "",
        "| Case / Run | Task | Tools | Workflow | Latency | Retries | Tool Failures | Issues |",
        "| --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        lines.append(
            f"| {_cell(result.case_id or result.run_id)} | {_status(result.task_success)} | "
            f"{_rate(result.tool_selection_accuracy)} | {_status(result.workflow_completed)} | "
            f"{result.latency:.4f}s | {result.retry_attempts} | {result.tool_failures} | "
            f"{', '.join(result.issues) or 'none'} |"
        )
    return "\n".join(lines) + "\n"


def write_markdown_report(
    results: Sequence[EvaluationResult], path: str | Path = "evaluation_report.md"
) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown_report(results), encoding="utf-8")
    return report_path
