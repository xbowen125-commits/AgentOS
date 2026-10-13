"""Fake by default; MiniLLM requires explicit --backend mini_llm and configuration.

Run: python -m examples.run_reliability_experiment --output results
Real: python -m examples.run_reliability_experiment --backend mini_llm
      --config configs/mini_llm.json --dataset YOUR_TASKS.json
This example supports only the synthetic status environment, not arbitrary domains.
"""

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agentos.core.agent import Agent
from agentos.evaluation import EvaluationRunner, EvaluationState, EvaluationTask
from agentos.evaluation.ablation import AblationPlanner, Variant, standard_variants
from agentos.evaluation.benchmark import TrialSession
from agentos.evaluation.experiment import ExperimentDataset, ExperimentRunner, ModelBackend
from agentos.events import AgentEvent, EventBus
from agentos.interfaces.model import Model
from agentos.memory.json_memory import JsonMemory
from agentos.models.fake import FakeModel
from agentos.models.mini_llm import MiniLLMConfig, MiniLLMModel
from agentos.planner.tool_prompt import ToolDescription
from agentos.tools.executor import ToolExecutor
from agentos.tools.metadata import describe_registry
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore
from examples.evaluation_demo import SetStatusTool


def session_factory(
    model: Model, variant: Variant, task: EvaluationTask, index: int,
) -> TrialSession:
    del index
    if set(task.initial_state) != {"status"} or set(task.goal_state) != {"status"}:
        raise ValueError("Demo dataset requires exactly the status environment field")
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
    agent = Agent(AblationPlanner(model, variant, tools, bus), ToolExecutor(registry),
                  JsonMemory(Path(directory.name) / "memory.json"), event_bus=bus)
    return TrialSession(EvaluationRunner(state, trace_store=traces), agent, events,
                        directory.cleanup)


def default_dataset() -> ExperimentDataset:
    return ExperimentDataset.from_data([{
        "task_id": "status-001", "description": "Use set_status to set status to done",
        "initial_state": {"status": "new"}, "goal_state": {"status": "done"},
        "expected_tools": ["set_status"], "metadata": {"environment": "synthetic-status"},
    }])


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("fake", "mini_llm"), default="fake")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--repeats", type=int, default=4)
    args = parser.parse_args()
    if any((args.output / name).exists() for name in (
        "benchmark.json", "failure_report.json", "experiment_report.md",
    )):
        parser.error("Output artifacts already exist; choose a new --output directory")
    dataset = ExperimentDataset.load(args.dataset) if args.dataset else default_dataset()
    if args.backend == "mini_llm":
        if args.config is None:
            parser.error("Real MiniLLM mode requires explicit --config; service is not auto-started")
        config = MiniLLMConfig(**json.loads(args.config.read_text(encoding="utf-8")))
        backend = ModelBackend("mini_llm", lambda: MiniLLMModel(config), {
            "adapter": "MiniLLMModel", "timeout": str(config.timeout),
            "max_tokens": str(config.max_tokens),
        })
    else:
        backend = ModelBackend("fake", lambda: FakeModel([
            '{"type":"tool_call","tool_name":"set_status","arguments":{"status":"done"}}',
            '{"type":"final","answer":"Done"}',
        ]), {"revision": "scripted-status-v1", "adapter": "FakeModel"})
    result = await ExperimentRunner(session_factory, repeats=args.repeats).run(
        dataset, [backend], standard_variants(),
    )
    for path in result.write(args.output):
        print(path)
    print(result.render_markdown())
    if args.backend == "mini_llm":
        print("Verify the loaded model revision separately; runtime phase counts are not HTTP counts.")


if __name__ == "__main__":
    asyncio.run(main())
