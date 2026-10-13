"""Versioned JSON task loading for reliability experiments."""

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentos.evaluation.task import EvaluationTask


@dataclass
class ExperimentTask(EvaluationTask):
    """Expected tools are annotations, not instructions or state success criteria."""

    expected_tools: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.expected_tools = self.expected_tools.copy()


@dataclass(frozen=True)
class ExperimentDataset:
    tasks: tuple[ExperimentTask, ...]
    digest: str

    @classmethod
    def from_data(cls, data: Any) -> "ExperimentDataset":
        """Validate the six task fields and reject non-portable JSON values."""
        if not isinstance(data, list) or not data:
            raise ValueError("Dataset must be a non-empty JSON task array")
        tasks = []
        required = {"task_id", "description", "initial_state", "goal_state",
                    "expected_tools", "metadata"}
        for entry in data:
            if not isinstance(entry, dict) or set(entry) != required:
                raise ValueError("Each task must contain exactly the six documented fields")
            if (not isinstance(entry["task_id"], str) or not entry["task_id"].strip()
                    or not isinstance(entry["description"], str)
                    or not entry["description"].strip()):
                raise ValueError("Task ID and description must be non-empty strings")
            for key in ("initial_state", "goal_state", "metadata"):
                if not isinstance(entry[key], dict):
                    raise ValueError(f"{key} must be an object")  # noqa: TRY004 -- dataset validation
            tools = entry["expected_tools"]
            if not isinstance(tools, list) or any(
                not isinstance(tool, str) or not tool.strip() for tool in tools
            ):
                raise ValueError("expected_tools must be an array of non-empty strings")
            tasks.append(ExperimentTask(**deepcopy(entry)))
        if len({task.task_id for task in tasks}) != len(tasks):
            raise ValueError("Task IDs must be unique")
        try:
            canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("Dataset must contain finite JSON-compatible data") from error
        return cls(tuple(tasks), hashlib.sha256(canonical.encode("utf-8")).hexdigest())

    @classmethod
    def load(cls, path: str | Path) -> "ExperimentDataset":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_object)
        except (ValueError, UnicodeError) as error:
            raise ValueError("Invalid benchmark dataset JSON") from error
        return cls.from_data(data)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result
