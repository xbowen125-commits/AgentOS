"""Model interfaces and deterministic adapters for AgentOS."""

from agentos.models.base import Model
from agentos.models.fake import FakeModel

__all__ = ["FakeModel", "Model"]
