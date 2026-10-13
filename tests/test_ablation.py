"""Mechanism switches, independent variants and all-k report metrics."""

import asyncio
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agentos.core.decision import ToolCallDecision
from agentos.core.state import AgentState
from agentos.evaluation import EvaluationTask
from agentos.evaluation.ablation import AblationPlanner, AblationRunner, Variant, standard_variants
from agentos.evaluation.benchmark import BenchmarkRunner
from agentos.events import EventBus
from agentos.exceptions import PlannerOutputError, RuntimeTimeoutError
from agentos.interfaces.model import Model
from agentos.models.fake import FakeModel
from agentos.planner.tool_prompt import ToolDescription
from examples.ablation_demo import factory


@pytest.mark.asyncio
async def test_parser_switch() -> None:
    output = '```json\n{"type":"final","answer":"ok"}\n```'
    with pytest.raises(PlannerOutputError):
        await AblationPlanner(FakeModel([output]), Variant("off")).plan(AgentState("test"))
    result = await AblationPlanner(FakeModel([output]), Variant(
        "on", parser_enabled=True,
    )).plan(AgentState("test"))
    assert result.answer == "ok"


@pytest.mark.asyncio
async def test_validator_and_retry_switches() -> None:
    tools = [ToolDescription("calculator", "calculate", {
        "type": "object", "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    })]
    invalid = '{"type":"tool_call","tool_name":"calculator","arguments":{}}'
    valid = '{"type":"tool_call","tool_name":"calculator","arguments":{"expression":"1+1"}}'
    state = AgentState("test")
    unchecked = await AblationPlanner(FakeModel([invalid]), Variant("off"), tools).plan(state)
    assert isinstance(unchecked, ToolCallDecision)
    with pytest.raises(PlannerOutputError):
        await AblationPlanner(FakeModel([invalid]), Variant(
            "validate", validator_enabled=True,
        ), tools).plan(state)
    events = []
    bus = EventBus()
    bus.subscribe(events.append)
    repaired = await AblationPlanner(FakeModel([invalid, valid]), Variant(
        "repair", validator_enabled=True, retry_enabled=True,
    ), tools, bus).plan(state)
    assert isinstance(repaired, ToolCallDecision) and repaired.arguments == {"expression": "1+1"}
    assert any(e.event_type == "planner.retry.completed" for e in events)


class SlowModel(Model):
    async def generate(self, prompt: str) -> str:
        await asyncio.sleep(0.02)
        return '{"type":"final","answer":"ok"}'


@pytest.mark.asyncio
async def test_timeout_switch() -> None:
    with pytest.raises(RuntimeTimeoutError):
        await AblationPlanner(SlowModel(), Variant(
            "timed", timeout_enabled=True, timeout_seconds=0.001,
        )).plan(AgentState("test"))
    assert await AblationPlanner(SlowModel(), Variant("untimed")).plan(AgentState("test"))


@pytest.mark.asyncio
async def test_variant_isolation_comparison_report(tmp_path: Path) -> None:
    created = []

    def isolated(variant: Variant, task: EvaluationTask, index: int):
        session = factory(variant, task, index)
        created.append(session)
        return session

    task = EvaluationTask("status", "Set status", {"status": "new"}, {"status": "done"})
    result = await AblationRunner(BenchmarkRunner(2, (1, 2))).run(
        [task], standard_variants(), isolated,
    )
    assert len({id(s.runner.state) for s in created}) == 10
    assert len({id(s.agent) for s in created}) == 10
    assert result.benchmarks["Baseline"].metrics.pass_at_1 == 0
    assert result.benchmarks["Parser"].metrics.pass_at_1 == 0.5
    assert result.benchmarks["Retry"].metrics.pass_power_k[2] == 1
    assert result.benchmarks["Full"].metrics.pass_at_1 == 1
    assert task.initial_state == {"status": "new"}
    text = result.render_markdown()
    assert "pass^2" in text and "Average Latency" in text
    assert "Failure Distribution" in text and "UNCLASSIFIED" in text
    assert result.write_markdown(tmp_path / "report.md").read_text(encoding="utf-8") == text


def test_variant_immutable_and_invalid_settings() -> None:
    variant = Variant("baseline")
    with pytest.raises(FrozenInstanceError):
        variant.name = "changed"
    with pytest.raises(ValueError):
        Variant("bad", timeout_seconds=float("nan"))
    with pytest.raises(ValueError):
        Variant("bad", max_retries=-1)


@pytest.mark.asyncio
async def test_duplicate_variants_rejected() -> None:
    with pytest.raises(ValueError):
        await AblationRunner().run([], [Variant("same"), Variant("same")], factory)
