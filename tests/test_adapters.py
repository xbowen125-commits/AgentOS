"""Tests for engine-neutral perception and action adapters."""

import json

import pytest

from agentos.adapters import InteractionAdapter, NPCAction, PerceptionEvent


def test_perception_event_is_json_serializable() -> None:
    event = PerceptionEvent.create("player.wave", {"confidence": 0.93})

    document = json.loads(json.dumps(event.to_dict()))

    assert document["event_type"] == "player.wave"
    assert document["payload"] == {"confidence": 0.93}


def test_interaction_adapter_converts_perception_events() -> None:
    adapter = InteractionAdapter()

    assert adapter.to_agent_input(PerceptionEvent.create("player.wave")) == "Player waved"
    assert (
        adapter.to_agent_input(PerceptionEvent.create("player.speech", {"text": "Hello"}))
        == "Player said: Hello"
    )


def test_speech_event_requires_structured_text() -> None:
    with pytest.raises(ValueError, match="requires non-empty"):
        InteractionAdapter().to_agent_input(PerceptionEvent.create("player.speech"))


def test_npc_action_serializes_for_internal_and_unity_protocols() -> None:
    action = NPCAction(
        action_type="speech",
        content="你好，又见面了",
        metadata={"animation": "wave"},
    )

    assert json.loads(json.dumps(action.to_dict(), ensure_ascii=False)) == {
        "action_type": "speech",
        "content": "你好，又见面了",
        "metadata": {"animation": "wave"},
    }
    assert action.to_unity_message() == {
        "type": "npc_action",
        "action": "wave",
        "text": "你好，又见面了",
    }
