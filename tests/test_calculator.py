"""Tests for the built-in calculator tool."""

import pytest

from agentos.tools.builtin.calculator import CalculatorTool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1+1", 2),
        ("2*3", 6),
        ("10/5", 2),
        ("-(2+3)", -5),
    ],
)
async def test_calculator_evaluates_basic_arithmetic(
    expression: str,
    expected: float,
) -> None:
    result = await CalculatorTool().execute(expression=expression)

    assert result == expected


@pytest.mark.asyncio
async def test_calculator_rejects_unsafe_expression() -> None:
    with pytest.raises(ValueError, match="Unsupported expression"):
        await CalculatorTool().execute(expression="__import__('os').getcwd()")
