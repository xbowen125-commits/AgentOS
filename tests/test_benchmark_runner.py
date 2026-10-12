"""Tests for trace-based benchmark execution."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from agentos.core.agent import Agent
from agentos.events import EventBus
from agentos.interfaces.model import Model
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore
from benchmarks.evaluator import (
    BenchmarkCase,
    BenchmarkRunner,
    BenchmarkRuntime,
    load_cases,
)
from tests.fakes.fake_mini_llm_server import FakeMiniLLMServer


def build_factory(tmp_path: Path, model_factory: Callable[[], Model]):
    def factory(case: BenchmarkCase) -> BenchmarkRuntime:
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        event_bus = EventBus()
        trace_store = JsonTraceStore(tmp_path / "traces")
        event_bus.subscribe(trace_store.append)
        agent = Agent(
            planner=ModelPlanner(model_factory()),
            tool_executor=ToolExecutor(registry),
            memory=JsonMemory(tmp_path / f"{case.id}.json"),
            event_bus=event_bus,
        )
        return BenchmarkRuntime(agent, trace_store)

    return factory


@pytest.mark.asyncio
async def test_runner_executes_case_with_fake_mini_llm_server(tmp_path: Path) -> None:
    server = FakeMiniLLMServer(
        responses=[
            json.dumps(
                {
                    "type": "tool_call",
                    "tool_name": "calculator",
                    "arguments": {"expression": "6*7"},
                }
            ),
            json.dumps({"type": "final", "answer": "42"}),
        ]
    )
    factory = build_factory(
        tmp_path,
        lambda: MiniLLMModel(
            MiniLLMConfig(base_url="http://mini-llm.test"),
            HttpClient(transport=server.transport),
        ),
    )
    case = BenchmarkCase("calc_success", "计算 6*7", "42", ("calculator",))

    benchmark = await BenchmarkRunner(factory).run([case])

    result = benchmark.results[0]
    assert result.success is True
    assert result.actual_answer == "42"
    assert result.model_calls == 2
    assert result.tool_calls == 1
    assert result.failure_reason is None
    assert benchmark.metrics.success_rate == 1.0


@pytest.mark.asyncio
async def test_runner_captures_agent_failure_and_continues(tmp_path: Path) -> None:
    factory = build_factory(tmp_path, lambda: FakeModel(["not-json"]))
    cases = [
        BenchmarkCase("broken_001", "invalid", "never", ("failure",)),
        BenchmarkCase("broken_002", "invalid again", "never", ("failure",)),
    ]

    benchmark = await BenchmarkRunner(factory).run(cases)

    assert len(benchmark.results) == 2
    assert benchmark.metrics.failed_cases == 2
    assert benchmark.metrics.success_rate == 0.0
    assert all(result.model_calls == 1 for result in benchmark.results)
    assert all("PlannerOutputError" in (result.failure_reason or "") for result in benchmark.results)


def test_bundled_cases_cover_required_scenarios() -> None:
    cases = load_cases()
    tags = {tag for case in cases for tag in case.tags}

    assert len(cases) >= 10
    assert "calculator" in tags
    assert "multi_step" in tags
    assert "invalid_input" in tags
    assert "tool_failure" in tags
