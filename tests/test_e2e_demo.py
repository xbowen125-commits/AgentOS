"""End-to-end test for the calculator agent example."""

import json
from pathlib import Path

import pytest

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.models.http_client import HttpClient
from examples.calculator_agent import build_runtime, get_final_answer
from tests.fakes.fake_mini_llm_server import FakeMiniLLMServer


@pytest.mark.asyncio
async def test_calculator_agent_runs_end_to_end_with_trace(tmp_path: Path) -> None:
    server = FakeMiniLLMServer(
        responses=[
            json.dumps(
                {
                    "type": "tool_call",
                    "tool_name": "calculator",
                    "arguments": {"expression": "123*456"},
                }
            ),
            json.dumps({"type": "final", "answer": "56088"}),
        ]
    )
    runtime = build_runtime(
        trace_directory=tmp_path / "traces",
        memory_path=tmp_path / "memory.json",
        http_client=HttpClient(transport=server.transport),
    )

    state = await runtime.agent.run("计算 123*456")

    assert state.finished is True
    assert state.step_count == 2
    assert isinstance(state.history[0], ToolCallDecision)
    assert state.history[1] == Observation(success=True, result="56088")
    assert isinstance(state.history[2], FinalAnswerDecision)
    assert get_final_answer(state) == "56088"
    assert len(server.requests) == 2
    second_request = json.loads(server.requests[1].content)
    assert "observation" in second_request["prompt"]
    assert "56088" in second_request["prompt"]

    trace = runtime.trace_store.load(state.run_id)
    trace_files = list((tmp_path / "traces").glob("run_*.json"))
    assert len(trace_files) == 1
    assert trace.run_id == state.run_id
    assert [event.event_type for event in trace.events] == [
        "agent.started",
        "planner.started",
        "model.called",
        "model.finished",
        "planner.finished",
        "tool.called",
        "tool.finished",
        "planner.started",
        "model.called",
        "model.finished",
        "planner.finished",
        "agent.finished",
    ]
