"""Agent runtime entry point."""

from typing import Any

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.state import AgentState
from agentos.events.bus import EventBus
from agentos.events.event import AgentEvent
from agentos.interfaces.memory import MemoryStore
from agentos.planner.planner import Planner
from agentos.tools.executor import ToolExecutor


class Agent:
    """Coordinate the minimal AgentOS runtime loop."""

    def __init__(
        self,
        planner: Planner,
        tool_executor: ToolExecutor,
        memory: MemoryStore,
        max_steps: int = 10,
        event_bus: EventBus | None = None,
    ) -> None:
        self.planner = planner
        self.tool_executor = tool_executor
        self.memory = memory
        self.max_steps = max_steps
        self.event_bus = event_bus

    async def run(self, user_input: str) -> AgentState:
        """Run planner decisions until completion or the step limit is reached."""
        state = AgentState(user_input=user_input)
        await self._emit("agent.started", state.run_id)

        try:
            while not state.finished and state.step_count < self.max_steps:
                step = state.step_count + 1
                await self._emit("planner.started", state.run_id, {"step": step})
                await self._emit("model.called", state.run_id, {"step": step})
                decision = await self.planner.plan(state)
                await self._emit("model.finished", state.run_id, {"step": step})
                await self._emit(
                    "planner.finished",
                    state.run_id,
                    {"step": step, "decision_type": type(decision).__name__},
                )
                state.step_count += 1
                state.history.append(decision)

                if isinstance(decision, FinalAnswerDecision):
                    state.finished = True
                    continue

                if isinstance(decision, ToolCallDecision):
                    await self._emit(
                        "tool.called",
                        state.run_id,
                        {"step": step, "tool_name": decision.tool_name},
                    )
                    observation = await self.tool_executor.execute(decision)
                    state.history.append(observation)
                    await self._emit(
                        "tool.finished",
                        state.run_id,
                        {
                            "step": step,
                            "tool_name": decision.tool_name,
                            "success": observation.success,
                            "error_type": observation.error_type,
                        },
                    )
                    continue

                raise TypeError(f"Unsupported planner decision: {type(decision).__name__}")
        except Exception as error:
            await self._emit(
                "agent.failed",
                state.run_id,
                {
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                },
            )
            raise

        await self._emit(
            "agent.finished",
            state.run_id,
            {"step_count": state.step_count, "finished": state.finished},
        )
        return state

    async def _emit(
        self,
        event_type: str,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Emit observability data without making it part of the runtime control path."""
        if self.event_bus is None:
            return
        try:
            await self.event_bus.emit(AgentEvent.create(event_type, run_id, payload))
        except Exception:  # noqa: BLE001
            return

