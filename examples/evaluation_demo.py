"""Offline state evaluation using the unchanged Agent and Tool Runtime."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agentos.core.agent import Agent
from agentos.evaluation import EvaluationRunner, EvaluationState, EvaluationTask
from agentos.events import EventBus
from agentos.interfaces.tool import Tool
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore


class SetStatusTool(Tool):
    name = "set_status"

    def __init__(self, state: EvaluationState) -> None:
        self.state = state

    async def execute(self, status: str) -> str:
        self.state.update({"status": status})
        return status


async def main() -> None:
    state = EvaluationState()
    task = EvaluationTask("status-001", "Set status to done", {"status": "new"},
                          {"status": "done"})
    with TemporaryDirectory() as directory:
        bus = EventBus()
        traces = JsonTraceStore(Path(directory) / "traces")
        bus.subscribe(traces.append)
        registry = ToolRegistry()
        registry.register(SetStatusTool(state))
        model = FakeModel([
            json.dumps({"type": "tool_call", "tool_name": "set_status",
                        "arguments": {"status": "done"}}),
            json.dumps({"type": "final", "answer": "Status updated"}),
        ])
        agent = Agent(ModelPlanner.from_registry(model, registry), ToolExecutor(registry),
                      JsonMemory(Path(directory) / "memory.json"), event_bus=bus)
        result = await EvaluationRunner(state, trace_store=traces).run(task, agent)
        print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
