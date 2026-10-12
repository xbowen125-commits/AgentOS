"""Complete offline Spatial AI NPC interaction demonstration."""

import asyncio
import json
import tempfile
from pathlib import Path

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

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def run_spatial_demo() -> dict[str, object]:
    """Execute one perception-to-action flow using temporary local adapters."""
    temporary_root = PROJECT_ROOT / "work"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="agentos_spatial_demo_",
        dir=temporary_root,
    ) as temporary_directory:
        runtime_directory = Path(temporary_directory)
        event_bus = EventBus()
        events: list[AgentEvent] = []
        trace_store = JsonTraceStore(runtime_directory / "traces")
        event_bus.subscribe(trace_store.append)
        event_bus.subscribe(events.append)

        memory_store = JsonMemory(runtime_directory / "memory.json")
        npc_memory = NPCMemory(memory_store)
        agent = Agent(
            planner=ModelPlanner(FakeModel(['{"type":"final","answer":"你好，很高兴见到你"}'])),
            tool_executor=ToolExecutor(ToolRegistry()),
            memory=memory_store,
            event_bus=event_bus,
        )
        adapter = InteractionAdapter(agent, event_bus, npc_memory)
        perception = PerceptionEvent.create("player.wave", {"confidence": 0.93})
        agent_input = adapter.to_agent_input(perception)
        action = await adapter.handle(perception, player_id="demo-player")
        profile = npc_memory.get_profile("demo-player")

        return {
            "perception_event": perception.to_dict(),
            "agent_input": agent_input,
            "npc_action": action.to_unity_message(),
            "player_profile": profile.to_dict(),
            "runtime_events": [event.event_type for event in events],
        }


def main() -> None:
    """Run the complete offline spatial interaction and print its public result."""
    print(json.dumps(asyncio.run(run_spatial_demo()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
