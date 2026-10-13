"""Planner backed by a replaceable Model interface."""

from collections.abc import Sequence

from agentos.core.state import AgentState
from agentos.events import EventBus
from agentos.interfaces.model import Model
from agentos.planner.parser import parse_decision
from agentos.planner.planner import AgentDecision, Planner
from agentos.planner.prompt import build_planner_prompt
from agentos.planner.retry import PlannerRetryController
from agentos.planner.tool_prompt import ToolDescription
from agentos.planner.validator import DecisionValidator


class ModelPlanner(Planner):
    """Request and normalize JSON decisions from a model adapter."""

    def __init__(
        self,
        model: Model,
        tools: Sequence[ToolDescription] | None = None,
        max_retries: int = 2,
        event_bus: EventBus | None = None,
        required_tool: str | None = None,
    ) -> None:
        self.model = model
        self.tools = tuple(tools or ())
        self.validator = DecisionValidator(tools, required_tool)
        self.retry_controller = PlannerRetryController(max_retries, event_bus)

    async def plan(self, state: AgentState) -> AgentDecision:
        prompt = build_planner_prompt(state, self.tools)
        if self.validator.required_tool is not None:
            prompt += (
                f"\nRequired tool for this task: {self.validator.required_tool}. "
                "Do not return final until this tool has a successful observation. "
                "The final answer must exactly equal that observation's result."
            )

        def parse_and_validate(output: str) -> AgentDecision:
            return self.validator.validate(self._parse_decision(output), state)

        return await self.retry_controller.generate_decision(
            self.model, prompt, parse_and_validate, state.run_id
        )

    def _parse_decision(self, output: str) -> AgentDecision:
        return parse_decision(output)
