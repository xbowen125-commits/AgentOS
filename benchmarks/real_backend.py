"""Opt-in benchmark runner for fake or real MiniLLM-Serve backends."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from agentos.core.agent import Agent
from agentos.events import EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.models.mini_llm import MiniLLMModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.tool_prompt import CALCULATOR_DESCRIPTION
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore
from benchmarks.evaluator import (
    DEFAULT_CASES_PATH,
    DEFAULT_OUTPUT_DIRECTORY,
    AgentFactory,
    BenchmarkCase,
    BenchmarkRunner,
    BenchmarkRuntime,
    build_offline_agent_factory,
    load_cases,
)
from benchmarks.report import render_markdown_report, write_markdown_report
from examples.real_mini_llm_agent import DEFAULT_CONFIG_PATH, load_config


def build_mini_llm_agent_factory(
    config_path: str | Path,
    output_directory: str | Path,
) -> AgentFactory:
    """Build benchmark agents that share one discovered MiniLLM model identity."""
    model = MiniLLMModel(load_config(config_path))
    output_path = Path(output_directory)

    def build(case: BenchmarkCase) -> BenchmarkRuntime:
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        event_bus = EventBus()
        trace_store = JsonTraceStore(output_path / "traces")
        event_bus.subscribe(trace_store.append)
        agent = Agent(
            planner=ModelPlanner(model, tools=[CALCULATOR_DESCRIPTION], event_bus=event_bus),
            tool_executor=ToolExecutor(registry),
            memory=JsonMemory(output_path / "memory" / f"{case.id}.json"),
            event_bus=event_bus,
        )
        return BenchmarkRuntime(agent, trace_store)

    return build


async def run_backend_benchmark(
    backend: str = "fake",
    *,
    cases_path: str | Path = DEFAULT_CASES_PATH,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    output_directory: str | Path = DEFAULT_OUTPUT_DIRECTORY,
) -> str:
    """Run the benchmark with real inference only when explicitly requested."""
    cases = load_cases(cases_path)
    output_path = Path(output_directory)
    if backend == "fake":
        factory = build_offline_agent_factory(output_path)
    elif backend == "mini_llm":
        factory = build_mini_llm_agent_factory(config_path, output_path / "real_backend")
    else:
        raise ValueError(f"Unsupported backend: {backend}")

    benchmark = await BenchmarkRunner(factory).run(cases)
    report = render_markdown_report(benchmark.metrics, benchmark.results)
    write_markdown_report(output_path / f"real_backend_{backend}.md", report)
    return report


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=("fake", "mini_llm"),
        default="fake",
        help="Inference backend. Real HTTP calls require the explicit mini_llm choice.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Parse CLI settings and print the generated Markdown report."""
    options = _parse_args(arguments)
    try:
        report = asyncio.run(
            run_backend_benchmark(
                options.backend,
                cases_path=options.cases,
                config_path=options.config,
                output_directory=options.output,
            )
        )
    except FileNotFoundError as error:
        print(f"Configuration or cases file not found: {error}")
        return 2
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
