"""Bounded structured-output repair and retry observability tests."""

import pytest

from agentos.core.decision import ToolCallDecision
from agentos.core.state import AgentState
from agentos.events import AgentEvent, EventBus
from agentos.exceptions import MiniLLMConnectionError, PlannerOutputError
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.planner.tool_prompt import CALCULATOR_DESCRIPTION


class RecordingModel(FakeModel):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return await super().generate(prompt)


@pytest.mark.asyncio
async def test_missing_arguments_are_repaired_and_events_are_sanitized() -> None:
    model = RecordingModel([
        '{"type":"tool_call","tool_name":"calculator"}',
        (
            '{"type":"tool_call","tool_name":"calculator",'
            '"arguments":{"expression":"123*456"}}'
        ),
    ])
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    state = AgentState("calculate", run_id="retry-run")
    planner = ModelPlanner(model, [CALCULATOR_DESCRIPTION], event_bus=bus)

    assert await planner.plan(state) == ToolCallDecision("calculator", {"expression": "123*456"})
    assert len(model.prompts) == 2
    assert "Missing required argument: expression" in model.prompts[1]
    assert "Available Tools:" in model.prompts[1]
    assert [event.event_type for event in events] == [
        "planner.retry.started", "planner.retry.completed",
    ]
    assert all(event.run_id == state.run_id for event in events)
    assert all(event.payload == {"attempt": 1} for event in events)
    assert state.history == []


@pytest.mark.asyncio
async def test_repeated_invalid_output_exhausts_exact_retry_budget() -> None:
    model = RecordingModel(["not-json"])
    bus = EventBus()
    events: list[AgentEvent] = []
    bus.subscribe(events.append)
    planner = ModelPlanner(model, max_retries=2, event_bus=bus)
    with pytest.raises(PlannerOutputError, match="after 2 retries"):
        await planner.plan(AgentState("task"))
    assert len(model.prompts) == 3
    assert [event.event_type for event in events] == [
        "planner.retry.started", "planner.retry.failed",
        "planner.retry.started", "planner.retry.failed",
    ]


@pytest.mark.asyncio
async def test_zero_retries_and_success_do_not_issue_extra_requests() -> None:
    model = RecordingModel(["invalid"])
    with pytest.raises(PlannerOutputError):
        await ModelPlanner(model, max_retries=0).plan(AgentState("task"))
    assert len(model.prompts) == 1
    valid = RecordingModel(['{"type":"final","answer":"done"}'])
    await ModelPlanner(valid).plan(AgentState("task"))
    assert len(valid.prompts) == 1


@pytest.mark.asyncio
async def test_transport_failure_is_not_retried() -> None:
    class BrokenModel(RecordingModel):
        async def generate(self, prompt: str) -> str:
            self.prompts.append(prompt)
            raise MiniLLMConnectionError("unavailable")

    model = BrokenModel(["unused"])
    with pytest.raises(MiniLLMConnectionError):
        await ModelPlanner(model).plan(AgentState("task"))
    assert len(model.prompts) == 1


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_invalid_retry_limit(value) -> None:
    with pytest.raises(ValueError):
        ModelPlanner(FakeModel(["invalid"]), max_retries=value)
