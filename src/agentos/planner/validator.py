"""Validate public decisions against tool contracts and execution evidence."""

import json
import math
from collections.abc import Sequence
from typing import Any

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.core.state import AgentState
from agentos.exceptions import PlannerOutputError
from agentos.planner.planner import AgentDecision
from agentos.planner.tool_prompt import ToolDescription


class DecisionValidator:
    """Enforce tool contracts and an optional task-specific required tool policy.

    required_tool is supplied by the application, rather than guessed from user text.
    Its final answer must equal the latest successful result from that tool.
    tools=None preserves legacy planners without declared tool contracts.
    An explicitly empty tools sequence allows no tool calls.
    """

    def __init__(
        self,
        tools: Sequence[ToolDescription] | None = (),
        required_tool: str | None = None,
    ) -> None:
        self.tools = None if tools is None else {tool.name: tool for tool in tools}
        if tools is not None and len(self.tools or {}) != len(tools):
            raise ValueError("Tool descriptions must have unique names")
        if required_tool is not None and (
            self.tools is None or required_tool not in self.tools
        ):
            raise ValueError("required_tool must exist in the declared tools")
        self.required_tool = required_tool

    def validate(self, decision: AgentDecision, state: AgentState) -> AgentDecision:
        """Return the unchanged decision, or raise a recoverable validation error."""
        if isinstance(decision, ToolCallDecision):
            self._validate_tool_call(decision)
        elif isinstance(decision, FinalAnswerDecision):
            if not isinstance(decision.answer, str) or not decision.answer.strip():
                raise PlannerOutputError("Final answer must not be empty")
            if self.required_tool is not None:
                observation = self._latest_observation(state)
                if observation is None or not observation.success or observation.result is None:
                    raise PlannerOutputError(
                        f"Final answer requires a successful {self.required_tool} observation. "
                        "Call the required tool with schema-valid arguments before finishing."
                    )
                if decision.answer != observation.result:
                    raise PlannerOutputError(
                        "Final answer must exactly equal the required tool observation result: "
                        f"{json.dumps(observation.result, ensure_ascii=False)}"
                    )
        else:
            raise PlannerOutputError("Unsupported decision type")
        return decision

    def _validate_tool_call(self, decision: ToolCallDecision) -> None:
        if self.tools is None:
            return
        tool = self.tools.get(decision.tool_name)
        if tool is None:
            raise PlannerOutputError("tool_name must exactly match an available tool")
        _validate_schema(decision.arguments, tool.input_schema, "arguments")

    def _latest_observation(self, state: AgentState) -> Observation | None:
        """Use only adjacent call/observation pairs for the required tool."""
        for index in range(len(state.history) - 1, -1, -1):
            item = state.history[index]
            if isinstance(item, ToolCallDecision) and item.tool_name == self.required_tool:
                next_item = state.history[index + 1] if index + 1 < len(state.history) else None
                return next_item if isinstance(next_item, Observation) else None
        return None


def _validate_schema(value: Any, schema: dict[str, Any], path: str) -> None:
    """Validate the JSON Schema subset used by AgentOS tool descriptions.

    Supports type, properties, required, additionalProperties, items, enum,
    maxLength/minLength, minimum/maximum, and minItems/maxItems.
    This is deliberately not a complete JSON Schema implementation.
    """
    supported = {
        "type", "properties", "required", "additionalProperties", "items", "enum",
        "maxLength", "minLength", "minimum", "maximum", "minItems", "maxItems",
        "description", "title",
    }
    if set(schema) - supported:
        raise PlannerOutputError(f"{path} uses an unsupported tool schema constraint")
    kind = schema.get("type")
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "null": value is None,
    }
    if kind is not None and not matches.get(kind, False):
        raise PlannerOutputError(f"{path} must have schema type {kind}")
    if isinstance(value, float) and not math.isfinite(value):
        raise PlannerOutputError(f"{path} must be finite")
    if "enum" in schema and value not in schema["enum"]:
        raise PlannerOutputError(f"{path} must match an allowed enum value")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise PlannerOutputError(f"Missing required argument: {name}")
        extra = set(value) - set(properties)
        if extra and schema.get("additionalProperties") is False:
            raise PlannerOutputError("arguments contain fields outside the tool schema")
        for name, item in value.items():
            child_schema = properties.get(name, schema.get("additionalProperties", {}))
            if isinstance(child_schema, dict):
                _validate_schema(item, child_schema, f"{path}.{name}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, (str, list)):
        minimum = "minLength" if isinstance(value, str) else "minItems"
        maximum = "maxLength" if isinstance(value, str) else "maxItems"
        if minimum in schema and len(value) < schema[minimum]:
            raise PlannerOutputError(f"{path} violates {minimum}")
        if maximum in schema and len(value) > schema[maximum]:
            raise PlannerOutputError(f"{path} violates {maximum}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise PlannerOutputError(f"{path} violates minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise PlannerOutputError(f"{path} violates maximum")
