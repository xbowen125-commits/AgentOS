"""Public tool contracts used only for planner prompt construction."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDescription:
    """Describe an available tool without depending on its runtime implementation."""

    name: str
    description: str
    input_schema: dict[str, Any]


CALCULATOR_DESCRIPTION = ToolDescription(
    name="calculator",
    description="Evaluate a mathematical expression using +, -, *, / and parentheses.",
    input_schema={
        "type": "object",
        "properties": {"expression": {"type": "string", "maxLength": 200}},
        "required": ["expression"],
        "additionalProperties": False,
    },
)


def build_tool_prompt(tools: Sequence[ToolDescription]) -> str:
    """Render explicit names and JSON schemas for the available tools."""
    sections = ["Available Tools:"]
    for tool in tools:
        sections.extend(
            [
                f"tool name: {tool.name}",
                f"description: {tool.description}",
                f"input schema: {json.dumps(tool.input_schema, ensure_ascii=False)}",
            ]
        )
    if not tools:
        sections.append("None. Do not emit tool_call decisions.")
    sections.extend(
        [
            "tool_name must exactly match an available tool name, including case.",
            "arguments must conform to that tool's input schema and include required fields.",
            "Never invent tools or argument fields.",
            "After a successful tool observation, base the final answer on its result.",
            "For a calculation, copy the observation result exactly into the final answer.",
            "If a tool fails, correct the call or report the failure; never invent a result.",
            "Return only the next decision, not both a tool call and a final answer.",
        ]
    )
    if any(tool.name == "calculator" for tool in tools):
        sections.append(
            "For arithmetic, call calculator with an expression string; do not calculate yourself."
        )
    return "\n".join(sections)
