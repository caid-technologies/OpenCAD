"""Safe math-expression evaluator for parametric bindings.

Only arithmetic operators and a small set of ``math`` functions are
permitted.  No attribute access, function calls beyond the whitelist,
or arbitrary Python execution.  Implemented via :mod:`ast` node walking.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

_BINARY_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "log": math.log,
    "log10": math.log10,
    "ceil": math.ceil,
    "floor": math.floor,
    "radians": math.radians,
    "degrees": math.degrees,
}

_SAFE_CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}


class ExpressionError(Exception):
    """Raised when an expression cannot be parsed or evaluated safely."""


def _eval_node(node: ast.AST, namespace: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, namespace)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ExpressionError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.Name):
        name = node.id
        if name in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[name]
        if name in namespace:
            return float(namespace[name])
        raise ExpressionError(f"Unknown symbol '{name}'")

    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise ExpressionError(f"Unsupported unary operator: {type(node.op).__name__}")
        return float(op_fn(_eval_node(node.operand, namespace)))

    if isinstance(node, ast.BinOp):
        op_fn = _BINARY_OPS.get(type(node.op))
        if op_fn is None:
            raise ExpressionError(f"Unsupported binary operator: {type(node.op).__name__}")
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.right, namespace)
        return float(op_fn(left, right))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExpressionError("Only simple function calls are allowed")
        fn = _SAFE_FUNCTIONS.get(node.func.id)
        if fn is None:
            raise ExpressionError(f"Function '{node.func.id}' is not allowed")
        args = [_eval_node(a, namespace) for a in node.args]
        if node.keywords:
            raise ExpressionError("Keyword arguments are not allowed")
        return float(fn(*args))

    raise ExpressionError(f"Unsupported expression node: {type(node).__name__}")


def evaluate(expression: str, namespace: dict[str, float] | None = None) -> float:
    """Evaluate a math expression string against *namespace* variables.

    >>> evaluate("2 * x + 1", {"x": 5})
    11.0
    >>> evaluate("sqrt(a**2 + b**2)", {"a": 3, "b": 4})
    5.0
    """
    ns = namespace or {}
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Invalid expression syntax: {exc}") from exc
    return _eval_node(tree, ns)


def extract_symbols(expression: str) -> set[str]:
    """Return all free variable names referenced in *expression*.

    Built-in constants (``pi``, ``e``) and function names are excluded.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Invalid expression syntax: {exc}") from exc

    names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            name = node.id
            if name not in _SAFE_CONSTANTS and name not in _SAFE_FUNCTIONS:
                names.add(name)
    return names
