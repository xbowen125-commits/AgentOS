"""Planner interface used by the agent runtime."""

from abc import ABC, abstractmethod

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.state import AgentState

AgentDecision = ToolCallDecision | FinalAnswerDecision


class Planner(ABC):
    """Choose the next action for an agent state."""

    @abstractmethod
    async def plan(self, state: AgentState) -> AgentDecision:
        """Return the next structured decision."""

