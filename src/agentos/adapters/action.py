"""Engine-neutral NPC action protocol."""

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class NPCAction:
    """A structured action returned to an external NPC environment."""

    action_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.action_type:
            raise ValueError("NPC action type must not be empty")
        if not isinstance(self.content, str):
            raise TypeError("NPC action content must be a string")
        if not isinstance(self.metadata, dict):
            raise TypeError("NPC action metadata must be a dictionary")
        try:
            json.dumps(asdict(self))
        except (TypeError, ValueError) as error:
            raise TypeError("NPC action must be JSON serializable") from error

    def to_dict(self) -> dict[str, Any]:
        """Return the internal adapter representation."""
        return asdict(self)

    def to_unity_message(self) -> dict[str, str]:
        """Return the minimal transport-neutral message expected by a Unity bridge."""
        animation = self.metadata.get("animation", self.action_type)
        if not isinstance(animation, str):
            animation = self.action_type
        return {
            "type": "npc_action",
            "action": animation,
            "text": self.content,
        }
