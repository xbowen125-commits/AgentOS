"""Deterministic state checking without model judgment."""

from typing import Any

from agentos.evaluation.result import EvaluationResult
from agentos.evaluation.task import EvaluationTask


def _equal(expected: Any, actual: Any) -> bool:
    # Do not treat True as 1 or 1.0 as an integer state value.
    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            _equal(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(
            _equal(left, right) for left, right in zip(expected, actual)
        )
    return bool(expected == actual)


class StateChecker:
    """Require exact values for goal keys; unrelated top-level keys are allowed."""

    def check(self, task: EvaluationTask, final_state: dict[str, Any]) -> EvaluationResult:
        checks = [
            {"key": key, "present": key in final_state,
             "matched": key in final_state and _equal(value, final_state[key])}
            for key, value in task.goal_state.items()
        ]
        success = all(check["matched"] for check in checks)
        return EvaluationResult(
            task.task_id, success, {"checks": checks},
            failure_type=None if success else "goal_mismatch",
        )
