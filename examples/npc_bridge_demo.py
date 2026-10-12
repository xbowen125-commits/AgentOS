"""Transport-neutral Spatial AI NPC bridge demonstration."""

import asyncio
import json
from pathlib import Path

from agentos.adapters import InteractionAdapter, PerceptionEvent
from agentos.core.agent import Agent
from agentos.events import EventBus
from agentos.memory.json_memory import JsonMemory
from agentos.memory.npc import NPCMemory
from agentos.models.fake import FakeModel
from agentos.planner.model_planner import ModelPlanner
from agentos.tools.executor import ToolExecutor
from agentos.tools.registry import ToolRegistry
from agentos.tracing import JsonTraceStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_demo_adapter() -> InteractionAdapter:
    """Assemble the protocol demo without Unity or network dependencies."""
    event_bus = EventBus()
    trace_store = JsonTraceStore(PROJECT_ROOT / "npc_traces")
    event_bus.subscribe(trace_store.append)
    memory_store = JsonMemory(PROJECT_ROOT / "npc_memory.json")
    agent = Agent(
        planner=ModelPlanner(FakeModel(['{"type":"final","answer":"你好"}'])),
        tool_executor=ToolExecutor(ToolRegistry()),
        memory=memory_store,
        event_bus=event_bus,
    )
    return InteractionAdapter(
        agent=agent,
        event_bus=event_bus,
        npc_memory=NPCMemory(memory_store),
    )


async def main() -> None:
    """Simulate one Unity message and print the bridge response."""
    unity_message = {"type": "player.wave"}
    event = PerceptionEvent.from_external(unity_message)
    action = await build_demo_adapter().handle(event, player_id="demo-player")

    print("Unity -> AgentOS:")
    print(json.dumps(unity_message, ensure_ascii=False, indent=2))
    print("\nAgentOS -> Unity:")
    print(json.dumps(action.to_unity_message(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
