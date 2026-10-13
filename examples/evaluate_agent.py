"""Generate an evaluation report from the existing deterministic benchmark cases."""

import asyncio
import json
from pathlib import Path

from agentos.core.decision import FinalAnswerDecision
from agentos.evaluation import EvaluationResult, Evaluator, write_markdown_report
from agentos.tracing import JsonTraceStore
from benchmarks.evaluator import build_offline_agent_factory, load_cases

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def evaluate_cases() -> Path:
    output = PROJECT_ROOT / "outputs" / "evaluation_report.md"
    evaluator = Evaluator(JsonTraceStore(PROJECT_ROOT / "traces" / "evaluation"))
    factory = build_offline_agent_factory(PROJECT_ROOT / "work" / "evaluation")
    results: list[EvaluationResult] = []
    for case in load_cases():
        runtime = factory(case)
        assert runtime.agent.event_bus is not None
        evaluator.subscribe(runtime.agent.event_bus)
        state = await runtime.agent.run(case.input)
        answer = next(
            (item.answer for item in reversed(state.history) if isinstance(item, FinalAnswerDecision)),
            None,
        )
        # The committed reference decisions define expected tool order for offline cases.
        reference = [json.loads(response) for response in case.model_responses]
        expected_tools = tuple(
            decision["tool_name"] for decision in reference if decision.get("type") == "tool_call"
        )
        assert evaluator.trace_store is not None
        results.append(evaluator.evaluate_case(
            evaluator.trace_store.load(state.run_id), case,
            actual_answer=answer, expected_tools=expected_tools,
        ))
    return write_markdown_report(results, output)


if __name__ == "__main__":
    report_path = asyncio.run(evaluate_cases())
    print(report_path.read_text(encoding="utf-8"))
    print(f"Report: {report_path}")
