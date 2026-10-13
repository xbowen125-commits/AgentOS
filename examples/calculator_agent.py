"""End-to-end calculator agent backed by MiniLLM-Serve."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision
from agentos.core.state import AgentState
from agentos.events import EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.models.http_client import HttpClient
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.tool_prompt import CALCULATOR_DESCRIPTION
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.json"
DEFAULT_TRACE_DIRECTORY = PROJECT_ROOT / "traces"
DEFAULT_MEMORY_PATH = PROJECT_ROOT / "memory.json"


@dataclass(frozen=True)
class DemoRuntime:
    """Dependencies assembled for the calculator demo."""

    agent: Agent
    trace_store: JsonTraceStore


def load_model_config(path: str | Path) -> MiniLLMConfig:
    """Load and validate the MiniLLM adapter configuration."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as config_file:
        document: Any = json.load(config_file)

    if not isinstance(document, dict) or not isinstance(document.get("model"), dict):
        raise TypeError("Configuration must contain a 'model' object")
    model = document["model"]
    if model.get("type") != "mini_llm":
        raise ValueError("Demo model type must be 'mini_llm'")
    base_url = model.get("base_url")
    if not isinstance(base_url, str):
        raise TypeError("Model 'base_url' must be a string")

    timeout = model.get("timeout", 30.0)
    max_tokens = model.get("max_tokens", 128)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise TypeError("Model 'timeout' must be a number")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
        raise TypeError("Model 'max_tokens' must be an integer")
    return MiniLLMConfig(
        base_url=base_url,
        timeout=float(timeout),
        max_tokens=max_tokens,
    )


def build_runtime(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    trace_directory: str | Path = DEFAULT_TRACE_DIRECTORY,
    memory_path: str | Path = DEFAULT_MEMORY_PATH,
    http_client: HttpClient | None = None,
) -> DemoRuntime:
    """Assemble the real AgentOS runtime with an injectable HTTP boundary."""
    model = MiniLLMModel(load_model_config(config_path), http_client=http_client)
    planner = ModelPlanner(model, tools=[CALCULATOR_DESCRIPTION])

    registry = ToolRegistry()
    registry.register(CalculatorTool())
    tool_executor = ToolExecutor(registry)

    event_bus = EventBus()
    trace_store = JsonTraceStore(trace_directory)
    event_bus.subscribe(trace_store.append)

    agent = Agent(
        planner=planner,
        tool_executor=tool_executor,
        memory=JsonMemory(memory_path),
        event_bus=event_bus,
    )
    return DemoRuntime(agent=agent, trace_store=trace_store)


def get_final_answer(state: AgentState) -> str:
    """Extract the public final answer from a completed run."""
    for item in reversed(state.history):
        if isinstance(item, FinalAnswerDecision):
            return item.answer
    raise RuntimeError("Agent run completed without a final answer")


async def main() -> None:
    """Run the interactive calculator demo."""
    user_input = input("User Input: ").strip()
    if not user_input:
        raise ValueError("User input must not be empty")

    runtime = build_runtime()
    state = await runtime.agent.run(user_input)

    print("\nFinal Answer:\n")
    print(get_final_answer(state))
    print(f"\nTrace written to: {DEFAULT_TRACE_DIRECTORY}")


if __name__ == "__main__":
    asyncio.run(main())
