"""Markdown evaluation reports without raw prompts or answer content."""

from collections.abc import Sequence
from pathlib import Path

from agentos.evaluation.benchmark import BenchmarkResult
from agentos.evaluation.evaluator import EvaluationResult
from agentos.evaluation.experiment import ExperimentResult
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


def render_reliability_report(result: BenchmarkResult | ExperimentResult) -> str:
    """Render categorical metrics only, preserving all v1 report functions."""
    results = result.results if isinstance(result, ExperimentResult) else {"benchmark": result}
    lines = ["# AgentOS Reliability Benchmark Report", ""]
    if isinstance(result, ExperimentResult):
        lines.extend([f"Baseline: {_cell(result.baseline)}", ""])
    for name, benchmark in results.items():
        metrics = benchmark.metrics
        lines.extend([
            f"## {_cell(name)}", "",
            f"Total Tasks: {metrics.total_tasks}", "",
            f"Trials: {metrics.total_trials}", "",
            "| Metric | Value |", "| --- | ---: |",
            f"| pass@1 | {_rate(metrics.pass_at_1)} |",
            f"| Success Rate | {_rate(metrics.success_rate)} |",
            f"| Observed Recovery Rate | {_rate(metrics.recovery_rate)} |",
        ])
        lines.extend(f"| pass^{k} | {_rate(value)} |"
                     for k, value in metrics.pass_power_k.items())
        lines.extend([
            "", f"Recovery coverage: {metrics.recovered_trials}/{metrics.recovery_trials}.",
            f"Trace coverage: {metrics.trace_covered_trials}/{metrics.total_trials}.", "",
            "### Failure Categories", "", "| Category | Failed Trials |", "| --- | ---: |",
        ])
        lines.extend(f"| {category} | {count} |"
                     for category, count in metrics.failure_distribution.items())
        if not metrics.failure_distribution:
            lines.append("| none | 0 |")
        lines.append("")
    lines.extend([
        "pass^k requires all k trials to succeed; it is not best-of-k.",
        "N/A indicates no applicable samples or k exceeding repeats.",
        "Recovery counts task success after an observed tool failure or planner repair attempt;",
        "missing events cannot demonstrate absence of failures. These prototype metrics do not",
        "constitute tau-bench results or statistical evidence of causal improvement.", "",
    ])
    return "\n".join(lines)


def write_reliability_report(
    result: BenchmarkResult | ExperimentResult,
    path: str | Path = "reliability_benchmark_report.md",
) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_reliability_report(result), encoding="utf-8")
    return report_path
