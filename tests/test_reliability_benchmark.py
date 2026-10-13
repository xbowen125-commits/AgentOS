"""Repeated trial isolation, consistency metrics and comparison reports."""

from pathlib import Path

import pytest

from agentos.core.state import AgentState as RuntimeState
from agentos.evaluation import EvaluationRunner, EvaluationState, EvaluationTask
from agentos.evaluation.benchmark import BenchmarkRunner, TrialSession
from agentos.evaluation.experiment import Experiment, ExperimentVariant
from agentos.evaluation.report import render_reliability_report, write_reliability_report
from agentos.events import AgentEvent


class ScriptedAgent:
    def __init__(self, state: EvaluationState, success: bool) -> None:
        self.state = state
        self.success = success

    async def run(self, user_input: str) -> RuntimeState:
        assert self.state.snapshot() == {"done": False}
        if self.success:
            self.state.update({"done": True})
        return RuntimeState(user_input, finished=True, run_id="test")


def task(name: str = "one") -> EvaluationTask:
    return EvaluationTask(name, "do task", {"done": False}, {"done": True})


def session(success: bool, recovery: bool = False) -> TrialSession:
    state = EvaluationState()
    events = [AgentEvent.create("planner.retry.started", "test")] if recovery else []
    return TrialSession(EvaluationRunner(state), ScriptedAgent(state, success), events)


@pytest.mark.asyncio
async def test_repeated_trials_and_exact_metrics() -> None:
    sessions = []

    def factory(current: EvaluationTask, index: int) -> TrialSession:
        created = session(index < 2 if current.task_id == "one" else True)
        sessions.append(created)
        return created

    result = await BenchmarkRunner(4, (1, 2, 4, 8)).run([task(), task("two")], factory)
    assert len(result.trials) == 8
    assert len({id(s.runner.state) for s in sessions}) == 8
    assert result.metrics.total_tasks == 2
    assert result.metrics.pass_at_1 == 0.75
    assert result.metrics.success_rate == 0.75
    assert result.metrics.pass_power_k[2] == pytest.approx((1 / 6 + 1) / 2)
    assert result.metrics.pass_power_k[4] == 0.5
    assert result.metrics.pass_power_k[8] is None
    assert result.metrics.failure_distribution == {"STATE_MISMATCH": 2}
    assert result.metrics.recovery_rate is None


@pytest.mark.asyncio
async def test_observed_recovery_and_failed_result_collection() -> None:
    result = await BenchmarkRunner(2, (1, 2)).run(
        [task()], lambda current, index: session(index == 0, recovery=True),
    )
    assert result.metrics.recovery_trials == 2
    assert result.metrics.recovered_trials == 1
    assert result.metrics.recovery_rate == 0.5
    assert result.trials[0].failure is None
    assert result.trials[1].failure is not None


@pytest.mark.asyncio
async def test_experiment_and_report(tmp_path: Path) -> None:
    experiment = Experiment(
        ExperimentVariant("baseline", lambda current, index: session(False)),
        [ExperimentVariant("variant", lambda current, index: session(True))],
        BenchmarkRunner(2, (1, 2)),
    )
    result = await experiment.run([task()])
    assert result.results["baseline"].metrics.pass_at_1 == 0
    assert result.results["variant"].metrics.pass_at_1 == 1
    text = render_reliability_report(result)
    assert "Baseline: baseline" in text
    assert "Total Tasks: 1" in text and "Trials: 2" in text
    assert "pass^2" in text and "STATE_MISMATCH" in text
    assert "N/A" in text
    path = write_reliability_report(result, tmp_path / "report.md")
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.asyncio
async def test_empty_tasks_and_cleanup() -> None:
    empty = await BenchmarkRunner().run([], lambda current, index: session(True))
    assert empty.metrics.pass_at_1 is None
    assert empty.metrics.total_trials == 0
    cleaned = []

    def factory(current: EvaluationTask, index: int) -> TrialSession:
        created = session(True)
        created.cleanup = lambda: cleaned.append(index)
        return created

    await BenchmarkRunner(2).run([task()], factory)
    assert cleaned == [0, 1]


@pytest.mark.asyncio
async def test_task_ids_and_factory_mutation() -> None:
    runner = BenchmarkRunner(2)
    with pytest.raises(ValueError, match="unique"):
        await runner.run([task(), task()], lambda current, index: session(True))

    def factory(current: EvaluationTask, index: int) -> TrialSession:
        current.goal_state["done"] = False
        return session(False)

    result = await runner.run([task()], factory)
    assert result.metrics.success_rate == 0


@pytest.mark.parametrize("repeats", [0, -1, True])
def test_invalid_repeats(repeats: int) -> None:
    with pytest.raises(ValueError):
        BenchmarkRunner(repeats)


def test_invalid_k_and_duplicate_variants() -> None:
    with pytest.raises(ValueError):
        BenchmarkRunner(k_values=(0,))
    variant = ExperimentVariant("same", lambda current, index: session(True))
    with pytest.raises(ValueError):
        Experiment(variant, [variant])


@pytest.mark.asyncio
async def test_runtime_failure_category_aggregation() -> None:
    class FailingAgent:
        async def run(self, user_input: str) -> RuntimeState:
            raise TimeoutError("private backend detail")

    def factory(current: EvaluationTask, index: int) -> TrialSession:
        return TrialSession(EvaluationRunner(EvaluationState()), FailingAgent(), [
            AgentEvent.create("agent.failed", "test", {"error_type": "RuntimeTimeoutError"}),
        ])

    result = await BenchmarkRunner(2).run([task()], factory)
    assert result.metrics.failure_distribution == {"TIMEOUT": 2}
    assert "private backend detail" not in render_reliability_report(result)


@pytest.mark.asyncio
async def test_cleanup_on_harness_error() -> None:
    cleaned = []

    def factory(current: EvaluationTask, index: int) -> TrialSession:
        state = EvaluationState()
        return TrialSession(EvaluationRunner(state), ScriptedAgent(
            state, True,
        ), [AgentEvent.create("agent.failed", "other")], lambda: cleaned.append(True))

    with pytest.raises(ValueError, match="different runs"):
        await BenchmarkRunner(1).run([task()], factory)
    assert cleaned == [True]
