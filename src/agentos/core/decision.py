"""Typed decisions produced by a planner."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCallDecision:
    """A decision to invoke a named tool with arguments."""

    tool_name: str
    arguments: dict[str, Any]


@dataclass
class FinalAnswerDecision:
    """A decision to return a final answer to the caller."""

    answer: str

