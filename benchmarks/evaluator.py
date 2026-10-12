"""Trace-based benchmark runner for AgentOS."""

import asyncio
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision
from agentos.events import AgentEvent, EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore, TraceRecord
from benchmarks.metrics import EvaluationMetrics
from benchmarks.report import render_markdown_report, write_markdown_report

BENCHMARK_DIRECTORY = Path(__file__).resolve().parent
DEFAULT_CASES_PATH = BENCHMARK_DIRECTORY / "cases.json"
DEFAULT_OUTPUT_DIRECTORY = BENCHMARK_DIRECTORY / "output"
_CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class BenchmarkCase:
    """One benchmark input and its expected public answer."""

    id: str
    input: str
    expected_answer: str
    tags: tuple[str, ...]
    model_responses: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkCase":
        """Validate and deserialize one case document."""
        case_id = data.get("id")
        user_input = data.get("input")
        expected_answer = data.get("expected_answer")
        tags = data.get("tags")
        raw_responses = data.get("model_responses", [])
        if not isinstance(case_id, str) or not _CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError("Benchmark case ID must use letters, numbers, '_' or '-'")
        if not isinstance(user_input, str):
            raise TypeError(f"Benchmark case {case_id!r} input must be a string")
        if not isinstance(expected_answer, str):
            raise TypeError(f"Benchmark case {case_id!r} expected_answer must be a string")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise TypeError(f"Benchmark case {case_id!r} tags must be a list of strings")
        if not isinstance(raw_responses, list):
            raise TypeError(f"Benchmark case {case_id!r} model_responses must be a list")

        responses: list[str] = []
        for response in raw_responses:
            if isinstance(response, str):
                responses.append(response)
            elif isinstance(response, dict):
                responses.append(json.dumps(response, ensure_ascii=False))
            else:
                raise TypeError(
                    f"Benchmark case {case_id!r} model response must be a string or object"
                )
        return cls(
            id=case_id,
            input=user_input,
            expected_answer=expected_answer,
            tags=tuple(tags),
            model_responses=tuple(responses),
        )


@dataclass(frozen=True)
class TraceAnalysis:
    """Measurements derived only from public runtime events."""

    latency: float
    model_calls: int
    tool_calls: int
    finished: bool
    failed: bool
    failure_reason: str | None


class TraceAnalyzer:
    """Compute execution measurements from a trace record."""

    @staticmethod
    def analyze(trace: TraceRecord) -> TraceAnalysis:
        """Count lifecycle events and calculate elapsed trace time."""
        timestamps = [datetime.fromisoformat(event.timestamp) for event in trace.events]
        latency = 0.0
        if len(timestamps) >= 2:
            latency = max(0.0, (timestamps[-1] - timestamps[0]).total_seconds())

        failure_event = next(
            (event for event in reversed(trace.events) if event.event_type == "agent.failed"),
            None,
        )
        failure_reason = None
        if failure_event is not None:
            error_type = failure_event.payload.get("error_type", "AgentError")
            error_message = failure_event.payload.get("error_message", "Unknown error")
            failure_reason = f"{error_type}: {error_message}"
        return TraceAnalysis(
            latency=latency,
            model_calls=sum(event.event_type == "model.called" for event in trace.events),
            tool_calls=sum(event.event_type == "tool.called" for event in trace.events),
            finished=any(event.event_type == "agent.finished" for event in trace.events),
            failed=failure_event is not None,
            failure_reason=failure_reason,
        )


@dataclass(frozen=True)
class BenchmarkResult:
    """Outcome and trace measurements for one benchmark case."""

    case_id: str
    success: bool
    actual_answer: str | None
    expected_answer: str
    latency: float
    model_calls: int
    tool_calls: int
    failure_reason: str | None = None


@dataclass(frozen=True)
class BenchmarkRun:
    """Case-level results and their aggregate metrics."""

    results: tuple[BenchmarkResult, ...]
    metrics: EvaluationMetrics


@dataclass(frozen=True)
class BenchmarkRuntime:
    """Agent and trace adapter used for one benchmark case."""

    agent: Agent
    trace_store: JsonTraceStore


AgentFactory = Callable[[BenchmarkCase], BenchmarkRuntime]


class BenchmarkRunner:
    """Execute benchmark cases through Agent.run and analyze their traces."""

    def __init__(self, agent_factory: AgentFactory) -> None:
        self.agent_factory = agent_factory

    async def run(self, cases: Sequence[BenchmarkCase]) -> BenchmarkRun:
        """Run cases sequentially so each measurement has isolated dependencies."""
        results = tuple([await self._run_case(case) for case in cases])
        return BenchmarkRun(results=results, metrics=EvaluationMetrics.from_results(results))

    async def _run_case(self, case: BenchmarkCase) -> BenchmarkResult:
        observed_events: list[AgentEvent] = []
        try:
            runtime = self.agent_factory(case)
        except Exception as error:  # noqa: BLE001
            return self._failed_result(case, f"Runtime setup failed: {type(error).__name__}: {error}")

        if runtime.agent.event_bus is None:
            return self._failed_result(case, "Runtime setup failed: Agent has no EventBus")
        runtime.agent.event_bus.subscribe(observed_events.append)

        try:
            state = await runtime.agent.run(case.input)
        except Exception as error:  # noqa: BLE001
            analysis = self._analyze_observed(runtime.trace_store, observed_events)
            reason = analysis.failure_reason or f"{type(error).__name__}: {error}"
            return self._result_from_analysis(case, analysis, None, False, reason)

        analysis = self._analyze_observed(runtime.trace_store, observed_events, state.run_id)
        actual_answer = self._find_final_answer(state.history)
        success = state.finished and not analysis.failed and actual_answer == case.expected_answer
        failure_reason = None
        if not success:
            if analysis.failure_reason is not None:
                failure_reason = analysis.failure_reason
            elif not state.finished:
                failure_reason = "Agent stopped before producing a final answer"
            elif actual_answer is None:
                failure_reason = "Agent produced no final answer"
            else:
                failure_reason = (
                    f"Answer mismatch: expected {case.expected_answer!r}, got {actual_answer!r}"
                )
        return self._result_from_analysis(
            case,
            analysis,
            actual_answer,
            success,
            failure_reason,
        )

    @staticmethod
    def _analyze_observed(
        trace_store: JsonTraceStore,
        events: list[AgentEvent],
        run_id: str | None = None,
    ) -> TraceAnalysis:
        resolved_run_id = run_id or (events[0].run_id if events else None)
        if resolved_run_id is None:
            return TraceAnalysis(0.0, 0, 0, False, True, "Agent emitted no runtime events")
        try:
            trace = trace_store.load(resolved_run_id)
        except Exception:  # noqa: BLE001
            trace = TraceRecord(run_id=resolved_run_id, events=events.copy())
        return TraceAnalyzer.analyze(trace)

    @staticmethod
    def _find_final_answer(history: list[Any]) -> str | None:
        for item in reversed(history):
            if isinstance(item, FinalAnswerDecision):
                return item.answer
        return None

    @staticmethod
    def _result_from_analysis(
        case: BenchmarkCase,
        analysis: TraceAnalysis,
        actual_answer: str | None,
        success: bool,
        failure_reason: str | None,
    ) -> BenchmarkResult:
        return BenchmarkResult(
            case_id=case.id,
            success=success,
            actual_answer=actual_answer,
            expected_answer=case.expected_answer,
            latency=analysis.latency,
            model_calls=analysis.model_calls,
            tool_calls=analysis.tool_calls,
            failure_reason=failure_reason,
        )

    @staticmethod
    def _failed_result(case: BenchmarkCase, reason: str) -> BenchmarkResult:
        return BenchmarkResult(case.id, False, None, case.expected_answer, 0.0, 0, 0, reason)


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[BenchmarkCase]:
    """Load benchmark cases from a JSON array."""
    with Path(path).open(encoding="utf-8") as cases_file:
        document: Any = json.load(cases_file)
    if not isinstance(document, list):
        raise TypeError("Benchmark cases document must be a JSON list")
    cases: list[BenchmarkCase] = []
    for index, item in enumerate(document):
        if not isinstance(item, dict):
            raise TypeError(f"Benchmark case at index {index} must be a JSON object")
        cases.append(BenchmarkCase.from_dict(dict(item)))
    return cases


def build_offline_agent_factory(output_directory: str | Path) -> AgentFactory:
    """Create isolated deterministic agents for the bundled offline benchmark."""
    output_path = Path(output_directory)

    def build(case: BenchmarkCase) -> BenchmarkRuntime:
        if not case.model_responses:
            raise ValueError(f"Benchmark case {case.id!r} has no offline model responses")
        planner = ModelPlanner(FakeModel(list(case.model_responses)))
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        event_bus = EventBus()
        trace_store = JsonTraceStore(output_path / "traces")
        event_bus.subscribe(trace_store.append)
        agent = Agent(
            planner=planner,
            tool_executor=ToolExecutor(registry),
            memory=JsonMemory(output_path / "memory" / f"{case.id}.json"),
            event_bus=event_bus,
        )
        return BenchmarkRuntime(agent=agent, trace_store=trace_store)

    return build


async def _run_default_benchmark() -> str:
    cases = load_cases()
    runner = BenchmarkRunner(build_offline_agent_factory(DEFAULT_OUTPUT_DIRECTORY))
    benchmark = await runner.run(cases)
    report = render_markdown_report(benchmark.metrics, benchmark.results)
    write_markdown_report(DEFAULT_OUTPUT_DIRECTORY / "report.md", report)
    return report


def main() -> None:
    """Run the bundled deterministic benchmark and print its Markdown report."""
    print(asyncio.run(_run_default_benchmark()))


if __name__ == "__main__":
    main()
