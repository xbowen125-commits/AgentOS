"""Validate the complete AgentOS loop against a running MiniLLM-Serve backend."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, ClassVar

from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision
from agentos.events import AgentEvent, EventBus
from agentos.exceptions import MiniLLMError
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
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "mini_llm.json"
DEFAULT_TRACE_DIRECTORY = PROJECT_ROOT / "traces" / "real_backend"
DEFAULT_MEMORY_PATH = PROJECT_ROOT / "work" / "real_backend_memory.json"
DEFAULT_INPUT = "计算 123*456"


@dataclass(frozen=True)
class RealBackendRuntime:
    """Dependencies and trace storage for a real-backend validation run."""

    agent: Agent
    trace_store: JsonTraceStore


@dataclass(frozen=True)
class RealBackendResult:
    """Public result and trace-derived measurements from one validation run."""

    answer: str
    run_id: str
    latency: float
    model_calls: int
    tool_calls: int
    trace_path: Path


class ValidationTraceHandler:
    """Persist runtime events plus stable validation-contract aliases."""

    _ALIASES: ClassVar[dict[str, str]] = {
        "planner.finished": "planner.decision",
        "agent.finished": "agent.completed",
    }

    def __init__(self, trace_store: JsonTraceStore) -> None:
        self.trace_store = trace_store

    def __call__(self, event: AgentEvent) -> None:
        self.trace_store.append(event)
        alias = self._ALIASES.get(event.event_type)
        if alias is not None:
            self.trace_store.append(
                AgentEvent.create(alias, event.run_id, dict(event.payload))
            )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> MiniLLMConfig:
    """Load the local, untracked MiniLLM-Serve connection configuration."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as config_file:
        document: Any = json.load(config_file)
    if not isinstance(document, dict):
        raise TypeError("MiniLLM configuration must be a JSON object")

    base_url = document.get("base_url")
    timeout = document.get("timeout", 30)
    max_tokens = document.get("max_tokens", 256)
    if not isinstance(base_url, str):
        raise TypeError("MiniLLM configuration 'base_url' must be a string")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise TypeError("MiniLLM configuration 'timeout' must be a number")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
        raise TypeError("MiniLLM configuration 'max_tokens' must be an integer")
    return MiniLLMConfig(base_url, timeout=float(timeout), max_tokens=max_tokens)


def build_runtime(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    trace_directory: str | Path = DEFAULT_TRACE_DIRECTORY,
    memory_path: str | Path = DEFAULT_MEMORY_PATH,
    http_client: HttpClient | None = None,
) -> RealBackendRuntime:
    """Assemble the unchanged Agent runtime around the real MiniLLM adapter."""
    model = MiniLLMModel(load_config(config_path), http_client=http_client)
    registry = ToolRegistry()
    registry.register(CalculatorTool())

    trace_store = JsonTraceStore(trace_directory)
    event_bus = EventBus()
    event_bus.subscribe(ValidationTraceHandler(trace_store))
    agent = Agent(
        planner=ModelPlanner(
            model,
            tools=[CALCULATOR_DESCRIPTION],
            event_bus=event_bus,
            required_tool="calculator",
        ),
        tool_executor=ToolExecutor(registry),
        memory=JsonMemory(memory_path),
        event_bus=event_bus,
    )
    return RealBackendRuntime(agent, trace_store)


async def run_validation(
    user_input: str = DEFAULT_INPUT,
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    trace_directory: str | Path = DEFAULT_TRACE_DIRECTORY,
    memory_path: str | Path = DEFAULT_MEMORY_PATH,
    http_client: HttpClient | None = None,
) -> RealBackendResult:
    """Run the real backend flow and summarize only public runtime events."""
    runtime = build_runtime(config_path, trace_directory, memory_path, http_client)
    started = perf_counter()
    state = await runtime.agent.run(user_input)
    elapsed = perf_counter() - started

    final = next(
        (item for item in reversed(state.history) if isinstance(item, FinalAnswerDecision)),
        None,
    )
    if final is None:
        raise RuntimeError("Agent completed without a final answer")

    trace = runtime.trace_store.load(state.run_id)
    event_types = [event.event_type for event in trace.events]
    required = {
        "agent.started",
        "planner.decision",
        "model.called",
        "tool.called",
        "agent.completed",
    }
    missing = sorted(required.difference(event_types))
    if missing:
        raise RuntimeError(f"Trace is missing required events: {', '.join(missing)}")

    digest = hashlib.sha256(state.run_id.encode("utf-8")).hexdigest()
    return RealBackendResult(
        answer=final.answer,
        run_id=state.run_id,
        latency=elapsed,
        model_calls=event_types.count("model.called"),
        tool_calls=event_types.count("tool.called"),
        trace_path=Path(trace_directory).resolve() / f"run_{digest}.json",
    )


def main() -> int:
    """Run validation without starting or managing MiniLLM-Serve."""
    try:
        result = asyncio.run(run_validation())
    except FileNotFoundError:
        print(
            "Configuration not found. Copy configs/mini_llm.example.json to "
            "configs/mini_llm.json and review the endpoint.",
            file=sys.stderr,
        )
        return 2
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"Invalid MiniLLM configuration: {error}", file=sys.stderr)
        return 2
    except MiniLLMError as error:
        print(
            f"MiniLLM-Serve is unavailable or returned an invalid response: {error}. "
            "Start the service separately and verify its /health endpoint.",
            file=sys.stderr,
        )
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"Agent validation failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print(f"User Input: {DEFAULT_INPUT}")
    print(f"Final Answer: {result.answer}")
    print(f"Latency: {result.latency:.4f}s")
    print(f"Model Calls: {result.model_calls}")
    print(f"Tool Calls: {result.tool_calls}")
    print(f"Trace: {result.trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
