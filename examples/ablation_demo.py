"""Controlled offline ablation; no real-model improvement claim."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agentos.core.agent import Agent
from agentos.evaluation import EvaluationRunner, EvaluationState, EvaluationTask
from agentos.evaluation.ablation import AblationPlanner, AblationRunner, Variant, standard_variants
from agentos.evaluation.benchmark import BenchmarkRunner, TrialSession
from agentos.events import AgentEvent, EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.tool_prompt import ToolDescription
from agentos.tools.executor import ToolExecutor
from agentos.tools.metadata import describe_registry
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore
from examples.evaluation_demo import SetStatusTool


def factory(variant: Variant, task: EvaluationTask, index: int) -> TrialSession:
    del task
    directory = TemporaryDirectory()
    state = EvaluationState()
    registry = ToolRegistry()
    registry.register(SetStatusTool(state))
    tools = [ToolDescription(m.name, m.description, m.input_schema)
             for m in describe_registry(registry)]
    events: list[AgentEvent] = []
    bus = EventBus()
    bus.subscribe(events.append)
    traces = JsonTraceStore(Path(directory.name) / "traces")
    bus.subscribe(traces.append)
    call = json.dumps({"type": "tool_call", "tool_name": "set_status",
                       "arguments": {"status": "done"}})
    # Identical fixtures across configurations: one fenced output, one malformed
    # initial output followed by a repairable response. Model reset each trial.
    outputs = ([f"```json\n{call}\n```"] if index % 2 == 0 else ["not JSON", call])
    outputs.append('{"type":"final","answer":"Done"}')
    planner = AblationPlanner(FakeModel(outputs), variant, tools, bus)
    agent = Agent(planner, ToolExecutor(registry),
                  JsonMemory(Path(directory.name) / "memory.json"), event_bus=bus)
    return TrialSession(EvaluationRunner(state, trace_store=traces), agent, events,
                        directory.cleanup)


async def main() -> None:
    task = EvaluationTask("status", "Set status to done", {"status": "new"}, {"status": "done"})
    result = await AblationRunner(BenchmarkRunner(2, (1, 2))).run(
        [task], standard_variants(), factory,
    )
    print("Synthetic FakeModel ablation: demonstrates switches, not real-model reliability.")
    print(result.render_markdown())


if __name__ == "__main__":
    asyncio.run(main())
