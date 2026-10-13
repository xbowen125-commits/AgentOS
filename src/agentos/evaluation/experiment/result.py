"""Portable categorical artifacts for multi-model reliability experiments."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentos.evaluation.ablation.result import AblationResult


@dataclass(frozen=True)
class ReliabilityExperimentResult:
    experiment_id: str
    manifest: dict[str, Any]
    models: dict[str, AblationResult]

    def benchmark_dict(self) -> dict[str, Any]:
        models = {}
        for model_name, ablation in self.models.items():
            variants = {}
            for variant in ablation.variants:
                benchmark = ablation.benchmarks[variant.name]
                variants[variant.name] = {
                    "configuration": asdict(variant), "metrics": asdict(benchmark.metrics),
                    "average_latency": (sum(t.result.latency for t in benchmark.trials)
                                        / len(benchmark.trials) if benchmark.trials else None),
                    "trials": [{"trial_index": trial.trial_index,
                                "result": trial.result.to_dict(),
                                "recovery_observed": trial.recovery_observed}
                               for trial in benchmark.trials],
                }
            models[model_name] = variants
        return {"schema_version": 1, "experiment_id": self.experiment_id,
                "manifest": self.manifest, "models": models}

    def failure_dict(self) -> dict[str, Any]:
        """Omit raw failure messages, which can contain model/user content."""
        failures = []
        for model_name, ablation in self.models.items():
            for variant_name, benchmark in ablation.benchmarks.items():
                for trial in benchmark.trials:
                    if trial.failure is not None:
                        failures.append({
                            "model": model_name, "variant": variant_name,
                            "task_id": trial.task_id, "trial_index": trial.trial_index,
                            "category": (trial.failure.category.value
                                         if trial.failure.category is not None else "UNCLASSIFIED"),
                            "step": trial.failure.step,
                            "evidence_ref": {
                                key: trial.failure.metadata[key]
                                for key in ("run_id", "event_type", "event_index", "error_type")
                                if key in trial.failure.metadata
                            },
                        })
        return {"schema_version": 1, "experiment_id": self.experiment_id,
                "raw_evidence_omitted": True, "failures": failures}

    def render_markdown(self) -> str:
        lines = ["# AgentOS Reliability Experiment Report", "",
                 f"Experiment: {self.experiment_id}", "",
                 f"Dataset digest: {self.manifest['dataset_digest']}", "",
                 ("Sequential prototype; pinned metadata is caller supplied. Missing revisions "
                  "are marked unknown. No causal or tau-bench score claims."), ""]
        for model_name, result in self.models.items():
            safe_name = model_name.replace("\n", " ").replace("\r", " ")
            lines.extend([f"## Model: {safe_name}", "", result.render_markdown(), ""])
            for variant_name, benchmark in result.benchmarks.items():
                metrics = benchmark.metrics
                name = variant_name.replace("\n", " ").replace("\r", " ")
                success = "N/A" if metrics.success_rate is None else f"{metrics.success_rate:.1%}"
                recovery = "N/A" if metrics.recovery_rate is None else f"{metrics.recovery_rate:.1%}"
                lines.append(f"- {name}: success rate={success}; observed recovery rate={recovery} "
                             f"({metrics.recovered_trials}/{metrics.recovery_trials}).")
            lines.append("")
        return "\n".join(lines)

    def write(self, directory: str | Path = "results") -> tuple[Path, Path, Path]:
        """Write named artifacts; callers should use a separate directory per experiment."""
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        benchmark = root / "benchmark.json"
        failure = root / "failure_report.json"
        report = root / "experiment_report.md"
        benchmark.write_text(json.dumps(self.benchmark_dict(), indent=2, ensure_ascii=False,
                                        allow_nan=False) + "\n", encoding="utf-8")
        failure.write_text(json.dumps(self.failure_dict(), indent=2, ensure_ascii=False,
                                      allow_nan=False) + "\n", encoding="utf-8")
        report.write_text(self.render_markdown(), encoding="utf-8")
        return benchmark, failure, report
