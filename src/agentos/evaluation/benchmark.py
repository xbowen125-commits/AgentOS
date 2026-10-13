"""Sequential repeated trials over the independent state evaluation runtime."""

from collections import Counter
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from math import comb

from agentos.evaluation.failure import FailureAnalysis, FailureAnalyzer
from agentos.evaluation.result import EvaluationResult
from agentos.evaluation.runner import EvaluationRunner, RunnableAgent
from agentos.evaluation.task import EvaluationTask
from agentos.events import AgentEvent


@dataclass
class TrialSession:
    """Factory-owned isolated agent/state; subscribe events.append to its bus.

    The factory must return fresh state, model, tools and event list each trial.
    An optional cleanup releases resources even when evaluation raises.
    """

    runner: EvaluationRunner
    agent: RunnableAgent
    events: list[AgentEvent] = field(default_factory=list)
    cleanup: Callable[[], None] | None = None


TrialFactory = Callable[[EvaluationTask, int], TrialSession]


@dataclass(frozen=True)
class BenchmarkTrial:
    task_id: str
    trial_index: int
    result: EvaluationResult
    failure: FailureAnalysis | None
    recovery_observed: bool


@dataclass(frozen=True)
class ReliabilityMetrics:
    total_tasks: int
    total_trials: int
    successful_trials: int
    pass_at_1: float | None
    pass_power_k: dict[int, float | None]
    success_rate: float | None
    recovery_rate: float | None
    recovery_trials: int
    recovered_trials: int
    trace_covered_trials: int
    failure_distribution: dict[str, int]


@dataclass(frozen=True)
class BenchmarkResult:
    trials: tuple[BenchmarkTrial, ...]
    metrics: ReliabilityMetrics


class BenchmarkRunner:
    """Fresh factory session for every trial, without modifying execution core.

    Recovery means task success after an observed failed tool attempt or planner
    retry.started; it is not recovery of a predeclared fault injection scenario.
    Event coverage is explicit; missing events cannot establish absence of errors.
    Factory/checker/cleanup errors propagate as harness errors, not agent failures.
    """

    def __init__(self, repeats: int = 10, k_values: Sequence[int] = (1, 2, 4, 8)) -> None:
        if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 1:
            raise ValueError("repeats must be a positive integer")
        if any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in k_values):
            raise ValueError("k values must be positive integers")
        self.repeats = repeats
        self.k_values = tuple(sorted(set(k_values)))

    async def run(
        self, tasks: Sequence[EvaluationTask], factory: TrialFactory,
    ) -> BenchmarkResult:
        tasks = deepcopy(tuple(tasks))
        if len({task.task_id for task in tasks}) != len(tasks):
            raise ValueError("Task IDs must be unique")
        trials: list[BenchmarkTrial] = []
        successes: list[int] = []
        analyzer = FailureAnalyzer()
        for task in tasks:
            successful = 0
            for index in range(self.repeats):
                trial_task = deepcopy(task)
                session = factory(deepcopy(trial_task), index)
                try:
                    result = await session.runner.run(trial_task, session.agent)
                    failure = analyzer.analyze(session.events, result)
                    recovery_observed = any(
                        event.event_type == "planner.retry.started"
                        or (event.event_type == "tool.finished"
                            and event.payload.get("success") is False)
                        for event in session.events
                    )
                    trials.append(BenchmarkTrial(task.task_id, index, result, failure,
                                                 recovery_observed))
                    successful += int(result.success)
                finally:
                    if session.cleanup is not None:
                        session.cleanup()
            successes.append(successful)
        total = len(trials)
        successful_total = sum(successes)
        recovery_trials = sum(trial.recovery_observed for trial in trials)
        recovered = sum(trial.recovery_observed and trial.result.success for trial in trials)
        distribution = Counter(
            trial.failure.category.value
            if trial.failure is not None and trial.failure.category is not None else "UNCLASSIFIED"
            for trial in trials if not trial.result.success
        )
        return BenchmarkResult(tuple(trials), ReliabilityMetrics(
            total_tasks=len(tasks), total_trials=total, successful_trials=successful_total,
            pass_at_1=sum(c / self.repeats for c in successes) / len(tasks) if tasks else None,
            pass_power_k={
                k: (sum(comb(c, k) / comb(self.repeats, k) for c in successes) / len(tasks)
                    if tasks and k <= self.repeats else None)
                for k in self.k_values
            },
            success_rate=successful_total / total if total else None,
            recovery_rate=recovered / recovery_trials if recovery_trials else None,
            recovery_trials=recovery_trials, recovered_trials=recovered,
            trace_covered_trials=sum(bool(t.result.evidence.get("trace_available")) for t in trials),
            failure_distribution=dict(sorted(distribution.items())),
        ))
