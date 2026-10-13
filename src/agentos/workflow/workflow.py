"""Multi-tool workflow composition without a second Agent execution loop."""

from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.core.state import AgentState
from agentos.events import AgentEvent, EventBus
from agentos.interfaces.memory import MemoryStore
from agentos.interfaces.model import Model
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.workflow.step import WorkflowStep


@dataclass(frozen=True)
class WorkflowResult:
    """Run state plus ordered snapshots of every executed tool attempt."""

    state: AgentState
    steps: tuple[WorkflowStep, ...]

    @property
    def answer(self) -> str | None:
        for item in reversed(self.state.history):
            if isinstance(item, FinalAnswerDecision):
                return item.answer
        return None

    @property
    def finished(self) -> bool:
        return self.state.finished

    @classmethod
    def from_state(cls, state: AgentState) -> "WorkflowResult":
        steps: list[WorkflowStep] = []
        decision_index = 0
        for index, item in enumerate(state.history):
            if isinstance(item, (ToolCallDecision, FinalAnswerDecision)):
                decision_index += 1
            if isinstance(item, ToolCallDecision) and index + 1 < len(state.history):
                observation = state.history[index + 1]
                if isinstance(observation, Observation):
                    steps.append(WorkflowStep(decision_index, deepcopy(item), deepcopy(observation)))
        return cls(state, tuple(steps))


class Workflow:
    """Compose a model planner, tool executor, and observable sequential Agent run.

    Tools are snapshotted from the registry at construction. Subsequent registration
    requires a new Workflow so prompt contracts stay consistent for each run.
    State is run-local; shared model/tool adapters must themselves support concurrency
    when a Workflow is invoked concurrently.
    """

    def __init__(
        self,
        model: Model,
        registry: ToolRegistry,
        memory: MemoryStore,
        max_steps: int = 10,
        max_retries: int = 2,
        event_bus: EventBus | None = None,
        required_tool: str | None = None,
    ) -> None:
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        self.event_bus = event_bus if event_bus is not None else EventBus()
        self._active_run: ContextVar[str | None] = ContextVar(
            f"workflow_run_{id(self)}", default=None
        )
        agent_events = EventBus()
        # Bind origin before public handlers can start a nested workflow.
        agent_events.subscribe(self._bind_run)
        agent_events.subscribe(self.event_bus.emit)
        agent_events.subscribe(self._observe)
        self.agent = Agent(
            planner=ModelPlanner.from_registry(
                model,
                registry,
                max_retries=max_retries,
                event_bus=agent_events,
                required_tool=required_tool,
            ),
            tool_executor=ToolExecutor(registry),
            memory=memory,
            max_steps=max_steps,
            event_bus=agent_events,
        )

    async def run(self, user_input: str) -> WorkflowResult:
        """Execute through Agent.run, then pair decisions with their observations."""
        token = self._active_run.set("")
        try:
            return WorkflowResult.from_state(await self.agent.run(user_input))
        finally:
            self._active_run.reset(token)

    def _bind_run(self, event: AgentEvent) -> None:
        if event.event_type == "agent.started" and self._active_run.get() == "":
            self._active_run.set(event.run_id)

    async def _observe(self, event: AgentEvent) -> None:
        if event.run_id != self._active_run.get():
            return
        if event.event_type == "agent.started":
            await self._emit("workflow.started", event, {})
        elif event.event_type == "tool.called":
            await self._emit("workflow.step.started", event, {
                "step": event.payload.get("step"), "tool_name": event.payload.get("tool_name"),
            })
        elif event.event_type == "tool.finished":
            success = event.payload.get("success") is True
            await self._emit(
                "workflow.step.completed" if success else "workflow.step.failed",
                event,
                {
                    "step": event.payload.get("step"),
                    "tool_name": event.payload.get("tool_name"),
                    "success": success,
                    "error_type": event.payload.get("error_type"),
                },
            )
        elif event.event_type == "agent.finished":
            finished = event.payload.get("finished") is True
            await self._emit("workflow.completed" if finished else "workflow.failed", event, {
                "step_count": event.payload.get("step_count"),
                "reason": None if finished else "step_limit",
            })
        elif event.event_type == "agent.failed":
            await self._emit("workflow.failed", event, {
                "error_type": event.payload.get("error_type"),
            })

    async def _emit(self, event_type: str, source: AgentEvent, payload: dict[str, Any]) -> None:
        try:
            await self.event_bus.emit(AgentEvent.create(event_type, source.run_id, payload))
        except Exception:  # noqa: BLE001
            return
