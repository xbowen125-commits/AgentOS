"""Structured long-term memory adapter for spatial NPC interactions."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from agentos.exceptions import MemoryItemNotFoundError
from agentos.interfaces.memory import MemoryStore
from agentos.memory.models import MemoryItem

NPC_PROFILE_TYPE = "npc_player_profile"


@dataclass(frozen=True)
class PlayerProfile:
    """Privacy-conscious interaction state stored for one player."""

    player_id: str
    interaction_count: int = 0
    last_action: str | None = None
    relationship_level: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return only the approved structured profile fields."""
        return asdict(self)


class NPCMemory:
    """Persist player profiles through the replaceable MemoryStore port."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_profile(self, player_id: str) -> PlayerProfile:
        """Return an existing profile or a new in-memory default."""
        self._validate_player_id(player_id)
        try:
            item = self.store.get(self._item_id(player_id))
        except MemoryItemNotFoundError:
            return PlayerProfile(player_id=player_id)
        return self._profile_from_item(item)

    def record_interaction(
        self,
        player_id: str,
        last_action: str,
        relationship_delta: int = 0,
    ) -> PlayerProfile:
        """Increment interaction state and persist the updated profile."""
        profile = self.get_profile(player_id)
        updated = PlayerProfile(
            player_id=player_id,
            interaction_count=profile.interaction_count + 1,
            last_action=last_action,
            relationship_level=self._relationship(profile.relationship_level + relationship_delta),
        )
        self._save(updated)
        return updated

    def update_relationship(self, player_id: str, delta: int) -> PlayerProfile:
        """Update only the bounded relationship level."""
        profile = self.get_profile(player_id)
        updated = PlayerProfile(
            player_id=profile.player_id,
            interaction_count=profile.interaction_count,
            last_action=profile.last_action,
            relationship_level=self._relationship(profile.relationship_level + delta),
        )
        self._save(updated)
        return updated

    def _save(self, profile: PlayerProfile) -> None:
        item_id = self._item_id(profile.player_id)
        try:
            created_at = self.store.get(item_id).created_at
        except MemoryItemNotFoundError:
            created_at = datetime.now(timezone.utc).isoformat()
        self.store.save(
            MemoryItem(
                id=item_id,
                type=NPC_PROFILE_TYPE,
                content=profile.to_dict(),
                created_at=created_at,
            )
        )

    @staticmethod
    def _profile_from_item(item: MemoryItem) -> PlayerProfile:
        if item.type != NPC_PROFILE_TYPE:
            raise ValueError(f"Memory item {item.id!r} is not an NPC player profile")
        content = item.content
        player_id = content.get("player_id")
        interaction_count = content.get("interaction_count")
        last_action = content.get("last_action")
        relationship_level = content.get("relationship_level")
        if not isinstance(player_id, str):
            raise TypeError("Stored player_id must be a string")
        if not isinstance(interaction_count, int) or isinstance(interaction_count, bool):
            raise TypeError("Stored interaction_count must be an integer")
        if last_action is not None and not isinstance(last_action, str):
            raise TypeError("Stored last_action must be a string or null")
        if not isinstance(relationship_level, int) or isinstance(relationship_level, bool):
            raise TypeError("Stored relationship_level must be an integer")
        return PlayerProfile(player_id, interaction_count, last_action, relationship_level)

    @staticmethod
    def _validate_player_id(player_id: str) -> None:
        if not player_id:
            raise ValueError("player_id must not be empty")

    @staticmethod
    def _item_id(player_id: str) -> str:
        return f"npc-player:{player_id}"

    @staticmethod
    def _relationship(value: int) -> int:
        return max(-100, min(100, value))
