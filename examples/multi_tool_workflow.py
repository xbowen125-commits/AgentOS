"""Offline calculator-to-formatter workflow using automatically discovered contracts."""

import asyncio
import json
from pathlib import Path

from agentos.events import EventBus
from agentos.interfaces.tool import Tool
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore
from agentos.workflow import Workflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FormatResultTool(Tool):
    """Format an observed calculator result for the user."""

    name = "format_result"

    async def execute(self, value: str) -> str:
        return f"Result: {value}"


async def main() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(FormatResultTool())
    responses = [
        {"type": "tool_call", "tool_name": "calculator", "arguments": {"expression": "123*456"}},
        {"type": "tool_call", "tool_name": "format_result", "arguments": {"value": "56088"}},
        {"type": "final", "answer": "Result: 56088"},
    ]
    bus = EventBus()
    trace_store = JsonTraceStore(PROJECT_ROOT / "traces" / "workflow")
    bus.subscribe(trace_store.append)
    workflow = Workflow(
        model=FakeModel([json.dumps(response) for response in responses]),
        registry=registry,
        memory=JsonMemory(PROJECT_ROOT / "work" / "workflow_memory.json"),
        event_bus=bus,
        required_tool="format_result",
    )
    result = await workflow.run("Calculate 123*456, then format the result for display.")
    for step in result.steps:
        print(f"Step {step.index}: {step.decision.tool_name} -> {step.observation.result}")
    print(f"Final: {result.answer}")
    print(f"Run ID: {result.state.run_id}")
    print(f"Trace directory: {trace_store.directory}")


if __name__ == "__main__":
    asyncio.run(main())
