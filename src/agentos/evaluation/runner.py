"""External trial orchestration over the existing Agent.run interface."""

from dataclasses import replace
from time import perf_counter
from typing import Protocol

from agentos.core.state import AgentState as RuntimeState
from agentos.evaluation.checker import StateChecker
from agentos.evaluation.result import EvaluationResult
from agentos.evaluation.state import AgentState
from agentos.evaluation.task import EvaluationTask
from agentos.tracing import JsonTraceStore


class RunnableAgent(Protocol):
    async def run(self, user_input: str) -> RuntimeState: ...


class EvaluationRunner:
    """Check independently updated state; sequential trials only.

    Tools/application adapters must share ``state``. A trace store, if supplied,
    must already be subscribed to the agent's EventBus. Counts represent observed
    model.called/tool.called phases, not actual backend HTTP requests.
    """

    def __init__(
        self, state: AgentState, checker: StateChecker | None = None,
        trace_store: JsonTraceStore | None = None,
    ) -> None:
        self.state = state
        self.checker = checker or StateChecker()
        self.trace_store = trace_store

    async def run(self, task: EvaluationTask, agent: RunnableAgent) -> EvaluationResult:
        self.state.reset(task.initial_state)
        started = perf_counter()
        runtime_state: RuntimeState | None = None
        failure_type: str | None = None
        exception_type: str | None = None
        try:
            runtime_state = await agent.run(task.description)
            if not runtime_state.finished:
                failure_type = "unfinished"
        except Exception as error:  # noqa: BLE001 -- report runtime failure, preserve cancellation
            failure_type = "runtime_error"
            exception_type = type(error).__name__
        latency = perf_counter() - started
        checked = self.checker.check(task, self.state.snapshot())
        evidence = dict(checked.evidence)
        evidence["trace_available"] = False
        if exception_type is not None:
            evidence["exception_type"] = exception_type
        model_calls = tool_calls = None
        if runtime_state is not None:
            evidence["run_id"] = runtime_state.run_id
            evidence["finished"] = runtime_state.finished
            if self.trace_store is not None:
                try:
                    trace = self.trace_store.load(runtime_state.run_id)
                    model_calls = sum(e.event_type == "model.called" for e in trace.events)
                    tool_calls = sum(e.event_type == "tool.called" for e in trace.events)
                    evidence["trace_available"] = True
                except Exception as error:  # noqa: BLE001 -- trace is optional evidence
                    evidence["trace_error_type"] = type(error).__name__
        return replace(
            checked, success=checked.success and failure_type is None, evidence=evidence,
            latency=latency, model_calls=model_calls, tool_calls=tool_calls,
            failure_type=failure_type or checked.failure_type,
        )
