"""Comparison artifacts retaining all benchmark trial evidence."""

from dataclasses import dataclass
from pathlib import Path

from agentos.evaluation.ablation.variant import Variant
from agentos.evaluation.benchmark import BenchmarkResult


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


@dataclass(frozen=True)
class AblationResult:
    variants: tuple[Variant, ...]
    benchmarks: dict[str, BenchmarkResult]

    def render_markdown(self) -> str:
        k_values = sorted({k for result in self.benchmarks.values()
                           for k in result.metrics.pass_power_k})
        columns = ["Variant", "Trials", "pass@1", *(f"pass^{k}" for k in k_values),
                   "Average Latency"]
        lines = ["# AgentOS Runtime Ablation Report", "",
                 "| " + " | ".join(columns) + " |",
                 "| " + " | ".join("---" for _ in columns) + " |"]
        for variant in self.variants:
            benchmark = self.benchmarks[variant.name]
            metrics = benchmark.metrics
            latency = (sum(t.result.latency for t in benchmark.trials) / len(benchmark.trials)
                       if benchmark.trials else None)
            cells = [_cell(variant.name), str(metrics.total_trials), _rate(metrics.pass_at_1),
                     *(_rate(metrics.pass_power_k.get(k)) for k in k_values),
                     f"{latency:.4f}s" if latency is not None else "N/A"]
            lines.append("| " + " | ".join(cells) + " |")
        lines.extend(["", "## Feature Configuration", "",
                      "| Variant | Parser | Validator | Retry | Timeout |",
                      "| --- | --- | --- | --- | --- |"])
        for variant in self.variants:
            lines.append(f"| {_cell(variant.name)} | {variant.parser_enabled} | "
                         f"{variant.validator_enabled} | {variant.retry_enabled} "
                         f"(max={variant.max_retries}) | {variant.timeout_enabled} "
                         f"({variant.timeout_seconds}s) |")
        lines.extend(["", "## Failure Distribution", "",
                      "| Variant | Category | Failed Trials |", "| --- | --- | ---: |"])
        for variant in self.variants:
            distribution = self.benchmarks[variant.name].metrics.failure_distribution
            for category, count in (distribution or {"none": 0}).items():
                lines.append(f"| {_cell(variant.name)} | {category} | {count} |")
        lines.extend(["", "## Evidence Coverage", ""])
        for variant in self.variants:
            metrics = self.benchmarks[variant.name].metrics
            lines.append(f"- {_cell(variant.name)}: tasks={metrics.total_tasks}, "
                         f"trace={metrics.trace_covered_trials}/{metrics.total_trials}.")
        lines.extend(["", ("pass^k measures all-k success, not best-of-k. N/A means insufficient "
                      "trials or no data. Average latency includes failed runs."),
                      ("Parser disabled means strict JSON decoding, not execution of raw text. "
                      "ToolExecutor contracts and sandbox boundaries remain active in Baseline."),
                      ("Timeout bounds one planner decision including repair requests; it does not "
                      "bound tool execution or the entire Agent run."),
                      ("Configurations run sequentially; no confidence intervals or causal "
                      "improvement claims are produced by this prototype."), ""])
        return "\n".join(lines)

    def write_markdown(self, path: str | Path = "ablation_report.md") -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render_markdown(), encoding="utf-8")
        return target
