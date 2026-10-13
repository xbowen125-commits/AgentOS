"""Contract snapshots generated from registered tools."""

import json
from typing import Any, ClassVar, Literal

import pytest

from agentos.interfaces.tool import Tool
from agentos.tools.builtin.calculator import CalculatorTool
from agentos.tools.metadata import ToolMetadata, describe_registry, describe_tool
from agentos.tools.registry import ToolRegistry


class TypedTool(Tool):
    """Format a labeled collection."""

    name = "format"

    async def execute(self, label: str, values: list[int], *, uppercase: bool = False) -> str:
        return label.upper() if uppercase else label


def test_calculator_declares_actual_contract() -> None:
    metadata = describe_tool(CalculatorTool())
    assert metadata.name == "calculator"
    assert "mathematical expression" in metadata.description
    assert metadata.input_schema == {
        "type": "object",
        "properties": {"expression": {"type": "string", "maxLength": 200}},
        "required": ["expression"],
        "additionalProperties": False,
    }
    assert json.loads(json.dumps(metadata.to_dict())) == metadata.to_dict()


def test_infers_typed_keyword_arguments_and_required_fields() -> None:
    metadata = describe_tool(TypedTool())
    assert metadata.description == "Format a labeled collection."
    assert metadata.input_schema == {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "values": {"type": "array", "items": {"type": "integer"}},
            "uppercase": {"type": "boolean"},
        },
        "required": ["label", "values"],
        "additionalProperties": False,
    }


def test_infers_nested_json_values_and_literals() -> None:
    class JsonTool(Tool):
        name = "json"

        async def execute(
            self, value: dict[str, list[float]], mode: Literal["short", "long"], extra: Any
        ) -> None:
            pass

    properties = describe_tool(JsonTool()).input_schema["properties"]
    assert properties["value"] == {
        "type": "object",
        "additionalProperties": {"type": "array", "items": {"type": "number"}},
    }
    assert properties["mode"] == {"type": "string", "enum": ["short", "long"]}
    assert properties["extra"] == {}


def test_unconstrained_kwargs_do_not_invent_fields() -> None:
    class OpenTool(Tool):
        name = "open"

        async def execute(self, **kwargs: Any) -> None:
            pass

    assert describe_tool(OpenTool()).input_schema == {
        "type": "object", "properties": {}, "required": [], "additionalProperties": True
    }


def test_registry_preserves_registration_order() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(TypedTool())
    assert [item.name for item in describe_registry(registry)] == ["calculator", "format"]
    assert describe_registry(ToolRegistry()) == ()


def test_snapshots_and_serialization_do_not_mutate_declared_schema() -> None:
    tool = CalculatorTool()
    first = describe_tool(tool)
    second = describe_tool(tool)
    exported = first.to_dict()
    exported["input_schema"]["properties"]["expression"]["type"] = "integer"
    first.input_schema["required"].append("extra")
    assert second.input_schema["properties"]["expression"]["type"] == "string"
    assert tool.input_schema["required"] == ["expression"]
    assert second.input_schema["required"] == ["expression"]


def test_metadata_copies_schema_on_construction() -> None:
    schema = {"type": "object", "required": ["key"]}
    metadata = ToolMetadata("lookup", "Look up a record.", schema)
    schema["required"].append("other")
    assert metadata.input_schema["required"] == ["key"]


def test_explicit_schema_takes_precedence_over_untyped_signature() -> None:
    class ExplicitTool(Tool):
        name = "explicit"
        description = "Read a named public value."
        input_schema: ClassVar[dict[str, Any]] = {
            "type": "object", "properties": {"key": {"type": "string"}}
        }

        async def execute(self, key):
            return key

    metadata = describe_tool(ExplicitTool())
    assert metadata.description == ExplicitTool.description
    assert metadata.input_schema == ExplicitTool.input_schema


def test_untyped_parameter_requires_explicit_contract() -> None:
    class UntypedTool(Tool):
        name = "untyped"

        async def execute(self, value):
            return value

    with pytest.raises(ValueError, match="type annotation or an explicit input_schema"):
        describe_tool(UntypedTool())


def test_unsupported_annotation_requires_explicit_contract() -> None:
    class UnsupportedTool(Tool):
        name = "unsupported"

        async def execute(self, value: bytes) -> bytes:
            return value

    with pytest.raises(ValueError, match="unsupported JSON input annotation"):
        describe_tool(UnsupportedTool())


def test_positional_only_parameter_requires_explicit_contract() -> None:
    class PositionalTool(Tool):
        name = "positional"

        async def execute(self, value: str, /) -> str:
            return value

    with pytest.raises(ValueError, match="unsupported positional parameters"):
        describe_tool(PositionalTool())


def test_non_json_schema_is_rejected() -> None:
    class NonJsonTool(CalculatorTool):
        input_schema: ClassVar[dict[str, Any]] = {"type": "object", "default": object()}

    with pytest.raises(ValueError, match="JSON serializable"):
        describe_tool(NonJsonTool())


def test_non_string_object_keys_are_rejected() -> None:
    class InvalidKeyTool(Tool):
        name = "invalid_key"

        async def execute(self, value: dict[int, str]) -> None:
            pass

    with pytest.raises(ValueError, match="JSON object keys must have type str"):
        describe_tool(InvalidKeyTool())


def test_explicit_schema_must_describe_keyword_object() -> None:
    class ArrayTool(CalculatorTool):
        input_schema: ClassVar[dict[str, Any]] = {"type": "array", "items": {"type": "string"}}

    with pytest.raises(ValueError, match="must describe a JSON object"):
        describe_tool(ArrayTool())


def test_numeric_literals_include_type_to_distinguish_booleans() -> None:
    class NumericTool(Tool):
        name = "numeric"

        async def execute(self, value: Literal[1, 2]) -> None:
            pass

    assert describe_tool(NumericTool()).input_schema["properties"]["value"] == {
        "type": "integer", "enum": [1, 2]
    }


def test_mixed_literal_types_require_explicit_schema() -> None:
    class MixedTool(Tool):
        name = "mixed"

        async def execute(self, value: Literal["one", 2]) -> None:
            pass

    with pytest.raises(ValueError, match="mixed JSON types"):
        describe_tool(MixedTool())
