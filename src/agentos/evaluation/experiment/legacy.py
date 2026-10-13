"""Compatible v1 baseline/variant API, retained after conversion to a package."""

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field

from agentos.evaluation.benchmark import BenchmarkResult, BenchmarkRunner, TrialFactory
from agentos.evaluation.task import EvaluationTask


@dataclass(frozen=True)
class ExperimentVariant:
    name: str
    factory: TrialFactory
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentResult:
    baseline: str
    results: dict[str, BenchmarkResult]
    configuration_metadata: dict[str, dict[str, str]] = field(default_factory=dict)


class Experiment:
    """Compare caller-assembled factories on the same tasks and repeat settings.

    This prototype runs configurations sequentially. It provides neither randomized
    scheduling nor confidence intervals; comparisons alone do not establish causality.
    """

    def __init__(
        self, baseline: ExperimentVariant, variants: Sequence[ExperimentVariant] = (),
        runner: BenchmarkRunner | None = None,
    ) -> None:
        self.configurations = (baseline, *variants)
        names = [variant.name for variant in self.configurations]
        if any(not name.strip() for name in names) or len(set(names)) != len(names):
            raise ValueError("Experiment names must be non-empty and unique")
        self.runner = runner or BenchmarkRunner()

    async def run(self, tasks: Sequence[EvaluationTask]) -> ExperimentResult:
        results = {}
        for variant in self.configurations:
            results[variant.name] = await self.runner.run(tasks, variant.factory)
        return ExperimentResult(self.configurations[0].name, results, {
            variant.name: deepcopy(variant.metadata) for variant in self.configurations
        })
