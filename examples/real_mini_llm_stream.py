"""Run the existing calculator Agent using native MiniLLM-Serve SSE decisions."""

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import aclosing

from agentos.core.agent import Agent
from agentos.events import AgentEvent, EventBus
from agentos.interfaces.model import Model
from agentos.memory.json_memory import JsonMemory
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.tool_prompt import CALCULATOR_DESCRIPTION
from agentos.streaming import StreamingManager
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore

if __package__:
    from examples.calculator_agent import get_final_answer
    from examples.real_mini_llm_agent import (
        DEFAULT_CONFIG_PATH,
        DEFAULT_INPUT,
        DEFAULT_MEMORY_PATH,
        DEFAULT_TRACE_DIRECTORY,
        RealBackendRuntime,
        ValidationTraceHandler,
        load_config,
    )
else:
    from calculator_agent import get_final_answer
    from real_mini_llm_agent import (
        DEFAULT_CONFIG_PATH,
        DEFAULT_INPUT,
        DEFAULT_MEMORY_PATH,
        DEFAULT_TRACE_DIRECTORY,
        RealBackendRuntime,
        ValidationTraceHandler,
        load_config,
    )


class StreamingPlannerModel(Model):
    """Example-only bridge: parse decisions after consuming a complete native stream."""

    def __init__(self, backend: Model, event_bus: EventBus) -> None:
        self.manager = StreamingManager(backend, event_bus)
        self.event_bus = event_bus

    async def generate(self, prompt: str) -> str:
        async with aclosing(
            self.manager.stream(prompt, run_id=self.event_bus.current_run_id)
        ) as stream:
            return "".join([token async for token in stream])

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        async with aclosing(
            self.manager.stream(prompt, run_id=self.event_bus.current_run_id)
        ) as stream:
            async for token in stream:
                yield token


def build_streaming_runtime(
    http_client: HttpClient | None = None,
) -> RealBackendRuntime:
    """Assemble native streaming around the unchanged Agent/Planner contracts."""
    bus = EventBus()
    trace_store = JsonTraceStore(DEFAULT_TRACE_DIRECTORY / "streaming")
    trace_handler = ValidationTraceHandler(trace_store)

    def metadata_trace(event: AgentEvent) -> None:
        # Live tokens are delivered to EventBus, but are not persisted by this demo.
        if event.event_type != "model.token":
            trace_handler(event)

    bus.subscribe(metadata_trace)
    model = StreamingPlannerModel(MiniLLMModel(load_config(), http_client), bus)
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    agent = Agent(
        planner=ModelPlanner(
            model, [CALCULATOR_DESCRIPTION], event_bus=bus, required_tool="calculator"
        ),
        tool_executor=ToolExecutor(registry),
        memory=JsonMemory(DEFAULT_MEMORY_PATH),
        event_bus=bus,
    )
    return RealBackendRuntime(agent, trace_store)


async def run_demo() -> None:
    runtime = build_streaming_runtime()

    def show_token(event: AgentEvent) -> None:
        if event.event_type == "model.token":
            print(event.payload["token"], end="", flush=True)
        elif event.event_type == "stream.finished":
            print()

    assert runtime.agent.event_bus is not None
    runtime.agent.event_bus.subscribe(show_token)
    state = await runtime.agent.run(DEFAULT_INPUT)
    print(f"Final Answer: {get_final_answer(state)}")
    print(f"Run ID: {state.run_id}")
    print(f"Trace directory: {runtime.trace_store.directory}")


def main() -> int:
    try:
        asyncio.run(run_demo())
    except FileNotFoundError:
        print(f"Configure MiniLLM-Serve in {DEFAULT_CONFIG_PATH} first.", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001
        print(f"Streaming demo failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
