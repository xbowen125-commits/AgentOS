"""Multi-model/variant experiments composed over Benchmark and Ablation."""

import platform
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from uuid import uuid4

from agentos.evaluation.ablation import AblationRunner, Variant
from agentos.evaluation.benchmark import BenchmarkRunner, TrialSession
from agentos.evaluation.experiment.dataset import ExperimentDataset
from agentos.evaluation.experiment.result import ReliabilityExperimentResult
from agentos.evaluation.task import EvaluationTask
from agentos.interfaces.model import Model


@dataclass(frozen=True)
class ModelBackend:
    """Explicit, fresh per-trial model creation; metadata must not contain secrets."""

    name: str
    create: Callable[[], Model]
    metadata: dict[str, str] = field(default_factory=dict)


SessionFactory = Callable[[Model, Variant, EvaluationTask, int], TrialSession]


class ExperimentRunner:
    """Models and environments are explicitly assembled; no automatic network activation.

    The session factory must apply variant switches and own model cleanup if needed.
    Models are freshly constructed per trial, with no cross-trial response cache.
    Expected tools are retained as annotations and never passed into the model prompt
    by this runner. State checker remains the success oracle.
    """

    def __init__(
        self, factory: SessionFactory, repeats: int = 10,
        k_values: Sequence[int] = (1, 2, 4, 8),
    ) -> None:
        self.factory = factory
        self.benchmark = BenchmarkRunner(repeats, k_values)

    async def run(
        self, dataset: ExperimentDataset, models: Sequence[ModelBackend],
        variants: Sequence[Variant],
    ) -> ReliabilityExperimentResult:
        models = tuple(models)
        variants = tuple(variants)
        if (not models or any(not m.name.strip() for m in models)
                or len({m.name for m in models}) != len(models)):
            raise ValueError("Models must be non-empty with unique non-empty names")
        if not variants or len({v.name for v in variants}) != len(variants):
            raise ValueError("Variants must be non-empty with unique names")
        # Re-validate mutable task objects and recompute identity at execution time.
        frozen_dataset = ExperimentDataset.from_data([asdict(t) for t in dataset.tasks])
        results = {}
        for backend in models:
            def build(variant: Variant, task: EvaluationTask, index: int,
                      backend: ModelBackend = backend) -> TrialSession:
                return self.factory(backend.create(), variant, task, index)

            results[backend.name] = await AblationRunner(self.benchmark).run(
                frozen_dataset.tasks, variants, build,
            )
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset_digest": frozen_dataset.digest,
            "task_count": len(frozen_dataset.tasks), "repeats": self.benchmark.repeats,
            "k_values": list(self.benchmark.k_values),
            "models": {m.name: {"revision": "unknown", **deepcopy(m.metadata)} for m in models},
            "variants": [asdict(v) for v in variants],
            "expected_tools": {t.task_id: t.expected_tools for t in frozen_dataset.tasks},
            "cache_policy": "fresh model per trial; factory must disable shared cache",
            "ordering": "sequential models, variants, tasks, trials",
            "python_version": platform.python_version(),
            "agentos_package_version": _package_version(),
            "source_revision": "unknown; record checkout revision in model metadata or archive",
        }
        return ReliabilityExperimentResult(str(uuid4()), manifest, results)


def _package_version() -> str:
    try:
        return version("agentos-runtime")
    except PackageNotFoundError:
        return "unknown"
