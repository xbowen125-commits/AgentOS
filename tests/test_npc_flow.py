"""End-to-end test for the external NPC interaction flow."""

from pathlib import Path

import pytest

from agentos.adapters import InteractionAdapter, PerceptionEvent
from agentos.core.agent import Agent
from agentos.events import AgentEvent, EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.memory.npc import NPCMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore


@pytest.mark.asyncio
async def test_perception_to_agent_to_npc_action_flow(tmp_path: Path) -> None:
    event_bus = EventBus()
    observed: list[AgentEvent] = []
    trace_store = JsonTraceStore(tmp_path / "traces")
    event_bus.subscribe(trace_store.append)
    event_bus.subscribe(observed.append)
    memory_store = JsonMemory(tmp_path / "memory.json")
    agent = Agent(
        planner=ModelPlanner(FakeModel(['{"type":"final","answer":"你好"}'])),
        tool_executor=ToolExecutor(ToolRegistry()),
        memory=memory_store,
        event_bus=event_bus,
    )
    adapter = InteractionAdapter(agent, event_bus, NPCMemory(memory_store))

    event = PerceptionEvent.from_external({"type": "player.wave"})
    action = await adapter.handle(event, player_id="player-1")

    assert action.to_unity_message() == {
        "type": "npc_action",
        "action": "wave",
        "text": "你好",
    }
    assert [event.event_type for event in observed] == [
        "interaction.received",
        "agent.started",
        "planner.started",
        "model.called",
        "model.finished",
        "planner.finished",
        "agent.finished",
        "npc.action.generated",
        "memory.updated",
    ]
    profile = NPCMemory(memory_store).get_profile("player-1")
    assert profile.interaction_count == 1
    assert profile.last_action == "wave"
    assert profile.relationship_level == 1

    action_event = next(event for event in observed if event.event_type == "npc.action.generated")
    action_trace = trace_store.load(action_event.run_id)
    assert action_trace.events[-2].event_type == "npc.action.generated"
    assert action_trace.events[-1].event_type == "memory.updated"
