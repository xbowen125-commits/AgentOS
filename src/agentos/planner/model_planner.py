"""Planner backed by a replaceable Model interface."""

from collections.abc import Sequence

from agentos.core.state import AgentState
from agentos.interfaces.model import Model
from agentos.planner.parser import parse_decision
from agentos.planner.planner import AgentDecision, Planner
from agentos.planner.prompt import build_planner_prompt
from agentos.planner.tool_prompt import ToolDescription


class ModelPlanner(Planner):
    """Request and normalize JSON decisions from a model adapter."""

    def __init__(self, model: Model, tools: Sequence[ToolDescription] = ()) -> None:
        self.model = model
        self.tools = tuple(tools)

    async def plan(self, state: AgentState) -> AgentDecision:
        prompt = build_planner_prompt(state, self.tools)
        output = await self.model.generate(prompt)
        return self._parse_decision(output)

    def _parse_decision(self, output: str) -> AgentDecision:
        return parse_decision(output)
