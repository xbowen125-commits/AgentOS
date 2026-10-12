"""Agent runtime entry point."""

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.state import AgentState
from agentos.interfaces.memory import Memory
from agentos.interfaces.model import Model
from agentos.interfaces.tool import Tool
from agentos.planner.planner import Planner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry


class Agent:
    """Coordinate the minimal AgentOS runtime loop."""

    def __init__(
        self,
        model: Model,
        planner: Planner,
        tools: list[Tool],
        memory: Memory,
        max_steps: int = 10,
    ) -> None:
        self.model = model
        self.planner = planner
        self.tools = tools
        self.memory = memory
        self.max_steps = max_steps
        self.tool_registry = ToolRegistry()
        for tool in tools:
            self.tool_registry.register(tool)
        self.tool_executor = ToolExecutor(self.tool_registry)

    async def run(self, user_input: str) -> AgentState:
        """Run planner decisions until completion or the step limit is reached."""
        state = AgentState(user_input=user_input)

        while not state.finished and state.step_count < self.max_steps:
            decision = await self.planner.plan(state)
            state.step_count += 1
            state.history.append(decision)

            if isinstance(decision, FinalAnswerDecision):
                state.finished = True
                continue

            if isinstance(decision, ToolCallDecision):
                observation = await self.tool_executor.execute(decision)
                state.history.append(observation)
                continue

            raise TypeError(f"Unsupported planner decision: {type(decision).__name__}")

        return state

