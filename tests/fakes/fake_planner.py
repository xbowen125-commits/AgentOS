"""Scripted planner used by agent loop tests."""

from agentos.core.state import AgentState
from agentos.planner.planner import AgentDecision, Planner


class FakePlanner(Planner):
    """Return a predefined sequence of decisions."""

    def __init__(self, decisions: list[AgentDecision]) -> None:
        self.decisions = decisions.copy()

    async def plan(self, state: AgentState) -> AgentDecision:
        if not self.decisions:
            raise RuntimeError("FakePlanner has no decisions remaining")
        return self.decisions.pop(0)
