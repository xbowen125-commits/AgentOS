"""Build public tool contracts from declarations or typed execute signatures."""

import inspect
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal, get_args, get_origin, get_type_hints

from agentos.interfaces.tool import Tool
from agentos.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolMetadata:
    """A snapshot of a tool's public name, description, and JSON input schema."""

    name: str
    description: str
    input_schema: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_schema", deepcopy(self.input_schema))

    def to_dict(self) -> dict[str, Any]:
        """Return an independent JSON-serializable metadata representation."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": deepcopy(self.input_schema),
        }


def describe_tool(tool: Tool) -> ToolMetadata:
    """Describe a tool without changing its registration or execution behavior.

    Tools can declare description and input_schema attributes. Otherwise the
    description comes from their docstring and the schema from execute's typed
    keyword parameters. Signatures that cannot represent a JSON object require
    an explicit schema; unconstrained **kwargs remain unconstrained.
    """
    name = getattr(tool, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Tool metadata requires a non-empty tool name")
    description = getattr(tool, "description", None)
    if description is None:
        description = inspect.getdoc(type(tool)) or f"Execute the {tool.name} tool."
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"Tool {tool.name!r} requires a non-empty description")

    declared_schema = getattr(tool, "input_schema", None)
    if declared_schema is not None:
        if not isinstance(declared_schema, dict) or declared_schema.get("type") != "object":
            raise ValueError(f"Tool {tool.name!r} input_schema must describe a JSON object")
        schema = deepcopy(declared_schema)
    else:
        schema = _infer_input_schema(tool)
    try:
        json.dumps(schema, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Tool {tool.name!r} input_schema must be JSON serializable") from error
    return ToolMetadata(tool.name, description, schema)


def describe_registry(registry: ToolRegistry) -> tuple[ToolMetadata, ...]:
    """Snapshot every registered tool in registration order."""
    return tuple(describe_tool(tool) for tool in registry.list_tools())


def _infer_input_schema(tool: Tool) -> dict[str, Any]:
    try:
        signature = inspect.signature(tool.execute)
        hints = get_type_hints(tool.execute)
    except (TypeError, ValueError, NameError) as error:
        raise ValueError(
            f"Cannot inspect tool {tool.name!r}; declare an explicit input_schema"
        ) from error

    properties: dict[str, Any] = {}
    required: list[str] = []
    additional_properties = False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            additional_properties = True
            continue
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            raise ValueError(
                f"Tool {tool.name!r} has unsupported positional parameters; "
                "declare an explicit input_schema"
            )
        annotation = hints.get(parameter.name, parameter.annotation)
        if annotation is inspect.Parameter.empty:
            raise ValueError(
                f"Tool {tool.name!r} parameter {parameter.name!r} needs a type annotation "
                "or an explicit input_schema"
            )
        try:
            properties[parameter.name] = _annotation_schema(annotation)
        except ValueError as error:
            raise ValueError(
                f"Tool {tool.name!r} parameter {parameter.name!r}: {error}; "
                "declare an explicit input_schema"
            ) from error
        if parameter.default is inspect.Parameter.empty:
            required.append(parameter.name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": additional_properties,
    }


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    if annotation is Any:
        return {}
    scalar_types = {str: "string", int: "integer", float: "number", bool: "boolean"}
    for scalar, kind in scalar_types.items():
        if annotation is scalar:
            return {"type": kind}
    if annotation is None or annotation is type(None):
        return {"type": "null"}

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if annotation is list or origin is list:
        return {"type": "array", "items": _annotation_schema(arguments[0]) if arguments else {}}
    if annotation is dict or origin is dict:
        if arguments and arguments[0] is not str:
            raise ValueError("JSON object keys must have type str")
        return {
            "type": "object",
            "additionalProperties": _annotation_schema(arguments[1]) if arguments else {},
        }
    if origin is Literal:
        if not all(value is None or type(value) in scalar_types for value in arguments):
            raise ValueError("Literal values must be JSON scalars")
        value_types = {type(value) for value in arguments}
        if value_types and value_types <= {int, float}:
            kind = "number" if float in value_types else "integer"
        elif len(value_types) == 1:
            value_type = next(iter(value_types))
            kind = "null" if value_type is type(None) else scalar_types[value_type]
        else:
            raise ValueError("Literal values with mixed JSON types need an explicit input_schema")
        return {"type": kind, "enum": list(arguments)}
    raise ValueError(f"unsupported JSON input annotation {annotation!r}")
