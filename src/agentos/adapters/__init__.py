"""External interaction adapters for AgentOS runtimes."""

from agentos.adapters.action import NPCAction
from agentos.adapters.interaction import InteractionAdapter
from agentos.adapters.perception import PerceptionEvent

__all__ = ["InteractionAdapter", "NPCAction", "PerceptionEvent"]
