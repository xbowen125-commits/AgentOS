"""Tests for privacy-conscious NPC player profile memory."""

from pathlib import Path

from agentos.memory.json_memory import JsonMemory
from agentos.memory.npc import NPCMemory


def test_npc_memory_counts_interactions_and_updates_relationship(tmp_path: Path) -> None:
    store = JsonMemory(tmp_path / "memory.json")
    memory = NPCMemory(store)

    first = memory.record_interaction("player-1", "wave", relationship_delta=1)
    second = memory.record_interaction("player-1", "talk", relationship_delta=2)
    updated = memory.update_relationship("player-1", -1)

    assert first.interaction_count == 1
    assert second.interaction_count == 2
    assert second.last_action == "talk"
    assert second.relationship_level == 3
    assert updated.interaction_count == 2
    assert updated.relationship_level == 2
    assert memory.get_profile("player-1") == updated


def test_npc_memory_persists_only_structured_profile_fields(tmp_path: Path) -> None:
    store = JsonMemory(tmp_path / "memory.json")
    memory = NPCMemory(store)

    memory.record_interaction("player-1", "wave")
    item = store.get("npc-player:player-1")

    assert set(item.content) == {
        "player_id",
        "interaction_count",
        "last_action",
        "relationship_level",
    }
    assert not {"face", "image", "audio", "biometric"}.intersection(item.content)
