"""Adapter between external perception events and the AgentOS API."""

from uuid import uuid4

from agentos.adapters.action import NPCAction
from agentos.adapters.perception import PerceptionEvent
from agentos.core.agent import Agent
from agentos.core.decision import FinalAnswerDecision
from agentos.events import AgentEvent, EventBus
from agentos.memory.npc import NPCMemory, PlayerProfile

_EVENT_INPUTS = {
    "player.detected": "Player detected",
    "player.wave": "Player waved",
    "player.look": "Player looked at the NPC",
}

_EVENT_ANIMATIONS = {
    "player.detected": "idle",
    "player.wave": "wave",
    "player.look": "look",
    "player.speech": "talk",
}

_RELATIONSHIP_DELTAS = {
    "player.detected": 0,
    "player.wave": 1,
    "player.look": 0,
    "player.speech": 1,
}


class InteractionAdapter:
    """Translate interaction events and orchestrate an optional Agent backend."""

    def __init__(
        self,
        agent: Agent | None = None,
        event_bus: EventBus | None = None,
        npc_memory: NPCMemory | None = None,
    ) -> None:
        self.agent = agent
        self.event_bus = event_bus or (agent.event_bus if agent is not None else None)
        self.npc_memory = npc_memory

    def to_agent_input(self, event: PerceptionEvent) -> str:
        """Convert a supported external event into a public Agent input string."""
        if event.event_type == "player.speech":
            speech = event.payload.get("text", event.payload.get("transcript"))
            if not isinstance(speech, str) or not speech.strip():
                raise ValueError("player.speech requires non-empty text or transcript")
            return f"Player said: {speech.strip()}"
        return _EVENT_INPUTS[event.event_type]

    async def handle(self, event: PerceptionEvent, player_id: str = "default") -> NPCAction:
        """Run one interaction through AgentOS and return an engine-neutral action."""
        if self.agent is None:
            raise RuntimeError("InteractionAdapter requires an Agent to handle events")

        interaction_id = str(uuid4())
        await self._emit(
            "interaction.received",
            interaction_id,
            {
                "interaction_id": interaction_id,
                "event_type": event.event_type,
                "player_id": player_id,
            },
        )
        state = await self.agent.run(self.to_agent_input(event))
        answer = self._final_answer(state.history)
        animation = _EVENT_ANIMATIONS[event.event_type]
        action = NPCAction(
            action_type="speech",
            content=answer,
            metadata={"animation": animation},
        )
        await self._emit(
            "npc.action.generated",
            state.run_id,
            {
                "interaction_id": interaction_id,
                "agent_run_id": state.run_id,
                "action": action.to_dict(),
            },
        )

        if self.npc_memory is not None:
            profile = self.npc_memory.record_interaction(
                player_id=player_id,
                last_action=animation,
                relationship_delta=_RELATIONSHIP_DELTAS[event.event_type],
            )
            await self._emit_memory_updated(state.run_id, interaction_id, profile)
        return action

    async def _emit_memory_updated(
        self,
        run_id: str,
        interaction_id: str,
        profile: PlayerProfile,
    ) -> None:
        await self._emit(
            "memory.updated",
            run_id,
            {
                "interaction_id": interaction_id,
                "player_profile": profile.to_dict(),
            },
        )

    async def _emit(self, event_type: str, run_id: str, payload: dict[str, object]) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.emit(AgentEvent.create(event_type, run_id, payload))

    @staticmethod
    def _final_answer(history: list[object]) -> str:
        for item in reversed(history):
            if isinstance(item, FinalAnswerDecision):
                return item.answer
        raise RuntimeError("Agent run completed without a final answer")
