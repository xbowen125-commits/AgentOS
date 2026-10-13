"""Extract and normalize public JSON planner decisions from model output."""

import json
from typing import Any

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.exceptions import PlannerOutputError
from agentos.planner.planner import AgentDecision


def _extract_object(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    text = output.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # raw_decode respects nested objects and braces inside JSON strings.
        # Only try top-level object starts, never salvage a nested tool argument.
        starts: list[int] = []
        depth = 0
        in_string = False
        escaped = False
        for index, character in enumerate(text):
            if depth and in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
            elif depth and character == '"':
                in_string = True
            elif character == "{":
                if depth == 0:
                    starts.append(index)
                depth += 1
            elif character == "}" and depth:
                depth -= 1

        objects: list[dict[str, Any]] = []
        for start in starts:
            try:
                candidate, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                objects.append(candidate)
        if not objects:
            raise PlannerOutputError("Model output is not valid JSON") from None
        if len(objects) != 1:
            raise PlannerOutputError("Model output contains multiple JSON objects")
        return objects[0]
    if not isinstance(data, dict):
        raise PlannerOutputError("Planner output must be a JSON object")
    return dict(data)


def _required_string(data: dict[str, Any], field: str) -> str:
    if field not in data:
        raise PlannerOutputError(f"Missing required field: {field}")
    value = data[field]
    if not isinstance(value, str) or not value.strip():
        raise PlannerOutputError(f"Field '{field}' must be a non-empty string")
    return value


def parse_decision(output: str) -> AgentDecision:
    """Normalize supported aliases, then validate the standard decision schema."""
    data = _extract_object(output)
    if "type" not in data and "name" in data:
        data = {**data, "type": "tool_call", "tool_name": data["name"]}
    decision_type = _required_string(data, "type")
    if decision_type == "final":
        return FinalAnswerDecision(answer=_required_string(data, "answer"))
    if decision_type != "tool_call":
        raise PlannerOutputError(f"Unknown decision type: {decision_type}")

    if "tool_name" not in data and "name" in data:
        data["tool_name"] = data["name"]
    tool_name = _required_string(data, "tool_name")
    arguments = data.get("arguments", data.get("input", {}))
    if isinstance(arguments, str) and tool_name == "calculator":
        arguments = {"expression": arguments}
    if not isinstance(arguments, dict):
        raise PlannerOutputError("Field 'arguments' must be a JSON object")
    return ToolCallDecision(tool_name=tool_name, arguments=dict(arguments))
