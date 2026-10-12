"""Prompt construction for the JSON model planner."""

import json
from typing import Any

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.observation import Observation
from agentos.core.state import AgentState


def build_planner_prompt(state: AgentState) -> str:
    """Build a prompt containing only task input, public history, and output schema."""
    history = [_serialize_history_item(item) for item in state.history]
    return (
        "Choose the next agent action. Return exactly one JSON object and no other text.\n"
        "Allowed outputs:\n"
        '{"type":"tool_call","tool_name":"<name>","arguments":{}}\n'
        '{"type":"final","answer":"<answer>"}\n'
        f"User input: {json.dumps(state.user_input, ensure_ascii=False)}\n"
        f"History: {json.dumps(history, ensure_ascii=False)}"
    )


def _serialize_history_item(item: Any) -> dict[str, Any]:
    if isinstance(item, ToolCallDecision):
        return {
            "type": "tool_call",
            "tool_name": item.tool_name,
            "arguments": item.arguments,
        }
    if isinstance(item, FinalAnswerDecision):
        return {"type": "final", "answer": item.answer}
    if isinstance(item, Observation):
        return {"type": "observation", **item.to_dict()}
    return {"type": "unsupported_history_item"}
