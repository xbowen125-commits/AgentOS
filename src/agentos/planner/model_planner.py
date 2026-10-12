"""Planner backed by a replaceable Model interface."""

import json
from typing import Any

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.state import AgentState
from agentos.exceptions import PlannerOutputError
from agentos.interfaces.model import Model
from agentos.planner.planner import AgentDecision, Planner
from agentos.planner.prompt import build_planner_prompt


class ModelPlanner(Planner):
    """Request and parse strict JSON decisions from a model adapter."""

    def __init__(self, model: Model) -> None:
        self.model = model

    async def plan(self, state: AgentState) -> AgentDecision:
        prompt = build_planner_prompt(state)
        output = await self.model.generate(prompt)
        return self._parse_decision(output)

    def _parse_decision(self, output: str) -> AgentDecision:
        try:
            data: Any = json.loads(output)
        except json.JSONDecodeError as error:
            raise PlannerOutputError("Model output is not valid JSON") from error

        if not isinstance(data, dict):
            raise PlannerOutputError("Planner output must be a JSON object")

        decision_type = self._required_string(data, "type")
        if decision_type == "tool_call":
            tool_name = self._required_string(data, "tool_name")
            if "arguments" not in data:
                raise PlannerOutputError("Missing required field: arguments")
            arguments = data["arguments"]
            if not isinstance(arguments, dict):
                raise PlannerOutputError("Field 'arguments' must be a JSON object")
            return ToolCallDecision(tool_name=tool_name, arguments=dict(arguments))

        if decision_type == "final":
            answer = self._required_string(data, "answer")
            return FinalAnswerDecision(answer=answer)

        raise PlannerOutputError(f"Unknown decision type: {decision_type}")

    @staticmethod
    def _required_string(data: dict[str, Any], field: str) -> str:
        if field not in data:
            raise PlannerOutputError(f"Missing required field: {field}")
        value = data[field]
        if not isinstance(value, str):
            raise PlannerOutputError(f"Field '{field}' must be a string")
        return value
