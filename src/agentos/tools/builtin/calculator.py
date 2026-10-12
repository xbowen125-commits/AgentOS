"""Safe arithmetic calculator tool."""

import ast
import operator
from collections.abc import Callable
from typing import Any

from agentos.interfaces.tool import Tool

Number = int | float
BinaryOperator = Callable[[Number, Number], Number]
UnaryOperator = Callable[[Number], Number]

_BINARY_OPERATORS: dict[type[ast.operator], BinaryOperator] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_UNARY_OPERATORS: dict[type[ast.unaryop], UnaryOperator] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorTool(Tool):
    """Evaluate expressions containing only basic arithmetic operations."""

    name = "calculator"

    async def execute(self, **kwargs: Any) -> Number:
        expression = kwargs.get("expression")
        if not isinstance(expression, str):
            raise TypeError("'expression' must be a string")

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as error:
            raise ValueError("Invalid mathematical expression") from error

        return self._evaluate(tree.body)

    def _evaluate(self, node: ast.AST) -> Number:
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return value

        if isinstance(node, ast.BinOp):
            binary_operation = _BINARY_OPERATORS.get(type(node.op))
            if binary_operation is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return binary_operation(self._evaluate(node.left), self._evaluate(node.right))

        if isinstance(node, ast.UnaryOp):
            unary_operation = _UNARY_OPERATORS.get(type(node.op))
            if unary_operation is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return unary_operation(self._evaluate(node.operand))

        raise ValueError(f"Unsupported expression: {type(node).__name__}")
