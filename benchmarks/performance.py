"""Performance aggregation and Markdown reporting for AgentOS traces."""

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentos.tracing import JsonTraceStore, RuntimeMetrics, TraceRecord

BENCHMARK_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_TRACE_DIRECTORY = BENCHMARK_DIRECTORY / "output" / "traces"
DEFAULT_REPORT_PATH = BENCHMARK_DIRECTORY / "output" / "performance.md"


@dataclass(frozen=True)
class PerformanceMetrics:
    """Aggregate stability and efficiency measurements across runtime traces."""

    run_count: int
    average_latency: float
    p95_latency: float
    model_calls: int
    tool_calls: int
    cache_hit_rate: float

    @classmethod
    def from_traces(cls, traces: Sequence[TraceRecord]) -> "PerformanceMetrics":
        """Aggregate latency, call counts, and cache effectiveness."""
        if not traces:
            return cls(0, 0.0, 0.0, 0, 0, 0.0)

        runtime_metrics = [RuntimeMetrics.from_trace(trace) for trace in traces]
        latencies = sorted(metrics.total_latency for metrics in runtime_metrics)
        percentile_index = max(0, math.ceil(len(latencies) * 0.95) - 1)
        cache_hits = sum(_event_count(trace, "cache.hit") for trace in traces)
        cache_misses = sum(_event_count(trace, "cache.miss") for trace in traces)
        cache_requests = cache_hits + cache_misses
        return cls(
            run_count=len(traces),
            average_latency=sum(latencies) / len(latencies),
            p95_latency=latencies[percentile_index],
            model_calls=sum(_event_count(trace, "model.called") for trace in traces),
            tool_calls=sum(_event_count(trace, "tool.called") for trace in traces),
            cache_hit_rate=cache_hits / cache_requests if cache_requests else 0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def load_traces(directory: str | Path) -> list[TraceRecord]:
    """Load every valid trace document from a JsonTraceStore directory."""
    trace_directory = Path(directory)
    if not trace_directory.exists():
        return []
    store = JsonTraceStore(trace_directory)
    traces: list[TraceRecord] = []
    for path in sorted(trace_directory.glob("run_*.json")):
        try:
            with path.open(encoding="utf-8") as trace_file:
                document: Any = json.load(trace_file)
            if not isinstance(document, dict) or not isinstance(document.get("run_id"), str):
                continue
            traces.append(store.load(document["run_id"]))
        except (OSError, ValueError):
            continue
    return traces


def render_performance_report(metrics: PerformanceMetrics) -> str:
    """Render performance metrics as Markdown."""
    return "\n".join(
        [
            "# AgentOS Performance Report",
            "",
            f"Runs: {metrics.run_count}",
            "",
            f"Average Latency: {metrics.average_latency:.4f}s",
            "",
            f"P95 Latency: {metrics.p95_latency:.4f}s",
            "",
            f"Model Calls: {metrics.model_calls}",
            "",
            f"Tool Calls: {metrics.tool_calls}",
            "",
            f"Cache Hit Rate: {metrics.cache_hit_rate:.1%}",
            "",
        ]
    )


def write_performance_report(path: str | Path, report: str) -> None:
    """Persist a rendered performance report."""
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def _event_count(trace: TraceRecord, event_type: str) -> int:
    return sum(event.event_type == event_type for event in trace.events)


def main() -> None:
    """Analyze bundled benchmark traces and write the performance report."""
    metrics = PerformanceMetrics.from_traces(load_traces(DEFAULT_TRACE_DIRECTORY))
    report = render_performance_report(metrics)
    write_performance_report(DEFAULT_REPORT_PATH, report)
    print(report)


if __name__ == "__main__":
    main()
