"""Offline repeated state trials; scripted data is not real-model quality."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agentos.core.agent import Agent
from agentos.evaluation import EvaluationRunner, EvaluationState, EvaluationTask
from agentos.evaluation.benchmark import BenchmarkRunner, TrialSession
from agentos.evaluation.experiment import Experiment, ExperimentVariant
from agentos.evaluation.report import render_reliability_report
from agentos.events import AgentEvent, EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore
from examples.evaluation_demo import SetStatusTool


def build_session(task: EvaluationTask, index: int, *, succeed: bool) -> TrialSession:
    """Fresh model, tools, state and temporary files for every trial."""
    del task, index
    directory = TemporaryDirectory()
    state = EvaluationState()
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    traces = JsonTraceStore(Path(directory.name) / "traces")
    bus.subscribe(traces.append)
    registry = ToolRegistry()
    registry.register(SetStatusTool(state))
    responses = []
    if succeed:
        responses.append(json.dumps({"type": "tool_call", "tool_name": "set_status",
                                     "arguments": {"status": "done"}}))
    responses.append(json.dumps({"type": "final", "answer": "Done"}))
    agent = Agent(
        ModelPlanner.from_registry(FakeModel(responses), registry), ToolExecutor(registry),
        JsonMemory(Path(directory.name) / "memory.json"), event_bus=bus,
    )
    return TrialSession(EvaluationRunner(state, trace_store=traces), agent, events,
                        directory.cleanup)


async def main() -> None:
    tasks = [EvaluationTask(f"status-{i}", "Set status to done", {"status": "new"},
                            {"status": "done"}) for i in range(2)]
    experiment = Experiment(
        ExperimentVariant("baseline-scripted", lambda task, index: build_session(
            task, index, succeed=index % 2 == 0,
        )),
        [ExperimentVariant("variant-scripted", lambda task, index: build_session(
            task, index, succeed=True,
        ))],
        BenchmarkRunner(repeats=4, k_values=(1, 2, 4)),
    )
    print("Scripted demonstration only; factories differ in fixture decisions, not model quality.")
    print(render_reliability_report(await experiment.run(tasks)))


if __name__ == "__main__":
    asyncio.run(main())
