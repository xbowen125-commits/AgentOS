"""Safe arithmetic calculator tool."""

import ast
import operator
from collections.abc import Callable
from typing import Any, cast

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
    max_expression_length = 200
    max_ast_nodes = 50
    max_integer_bits = 256

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        unexpected = set(arguments) - {"expression"}
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise TypeError(f"unexpected arguments: {names}")
        if "expression" not in arguments:
            raise TypeError("missing required argument: 'expression'")
        if not isinstance(arguments["expression"], str):
            raise TypeError("'expression' must be a string")

    async def execute(self, **kwargs: Any) -> Number:
        self.validate_arguments(kwargs)
        expression = cast(str, kwargs["expression"])
        if len(expression) > self.max_expression_length:
            raise ValueError(
                f"Expression exceeds maximum length of {self.max_expression_length} characters"
            )

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as error:
            raise ValueError("Invalid mathematical expression") from error

        node_count = sum(1 for _ in ast.walk(tree))
        if node_count > self.max_ast_nodes:
            raise ValueError(f"Expression exceeds maximum AST size of {self.max_ast_nodes} nodes")

        return self._evaluate(tree.body)

    def _evaluate(self, node: ast.AST) -> Number:
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return self._validate_number(value)

        if isinstance(node, ast.BinOp):
            binary_operation = _BINARY_OPERATORS.get(type(node.op))
            if binary_operation is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            result = binary_operation(self._evaluate(node.left), self._evaluate(node.right))
            return self._validate_number(result)

        if isinstance(node, ast.UnaryOp):
            unary_operation = _UNARY_OPERATORS.get(type(node.op))
            if unary_operation is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return self._validate_number(unary_operation(self._evaluate(node.operand)))

        raise ValueError(f"Unsupported expression: {type(node).__name__}")

    def _validate_number(self, value: Number) -> Number:
        if isinstance(value, int) and value.bit_length() > self.max_integer_bits:
            raise ValueError(f"Integer exceeds maximum size of {self.max_integer_bits} bits")
        return value
