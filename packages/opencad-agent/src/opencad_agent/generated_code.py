from __future__ import annotations

import ast
import importlib
from types import ModuleType
from typing import Any

ALLOWED_OPENCAD_IMPORTS = {"Part", "Sketch"}
BLOCKED_MODULE_NAMES = {
    "builtins",
    "importlib",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "urllib",
}
BLOCKED_CALL_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
BLOCKED_STATEMENTS = (
    ast.AsyncFor,
    ast.AsyncFunctionDef,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.For,
    ast.FunctionDef,
    ast.Global,
    ast.Lambda,
    ast.Match,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    ast.While,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
)


class GeneratedCodePolicyError(ValueError):
    """Raised when generated OpenCAD code uses APIs outside the supported subset."""


def validate_generated_code(code: str) -> ast.Module:
    try:
        tree = ast.parse(code, filename="<generated-opencad-code>", mode="exec")
    except SyntaxError as exc:
        raise GeneratedCodePolicyError(f"Generated code is not valid Python: {exc.msg}") from exc

    for node in ast.walk(tree):
        _validate_node(node)
    _validate_sketch_profiles(tree)
    return tree


def execute_generated_code(code: str) -> None:
    tree = validate_generated_code(code)
    namespace = _execution_namespace()
    exec(compile(tree, "<generated-opencad-code>", "exec"), namespace)  # noqa: S102


def _validate_node(node: ast.AST) -> None:
    if isinstance(node, ast.Import):
        raise GeneratedCodePolicyError("Generated code may only import Part and Sketch from opencad.")
    if isinstance(node, ast.ImportFrom):
        _validate_import_from(node)
        return
    if isinstance(node, BLOCKED_STATEMENTS):
        raise GeneratedCodePolicyError(f"Generated code cannot use {type(node).__name__} statements.")
    if isinstance(node, ast.Name):
        _validate_name(node.id)
        return
    if isinstance(node, ast.Attribute):
        _validate_attribute(node)
        return
    if isinstance(node, ast.Call):
        _validate_call(node)


def _validate_import_from(node: ast.ImportFrom) -> None:
    if node.level != 0 or node.module != "opencad":
        raise GeneratedCodePolicyError("Generated code may only import Part and Sketch from opencad.")
    imported = {alias.name for alias in node.names}
    if not imported or imported - ALLOWED_OPENCAD_IMPORTS:
        raise GeneratedCodePolicyError("Generated code may only import Part and Sketch from opencad.")
    if any(alias.asname is not None for alias in node.names):
        raise GeneratedCodePolicyError("Generated code may not alias OpenCAD imports.")


def _validate_name(name: str) -> None:
    if name.startswith("__") or name in BLOCKED_MODULE_NAMES:
        raise GeneratedCodePolicyError(f"Generated code cannot reference {name!r}.")


def _validate_attribute(node: ast.Attribute) -> None:
    if node.attr.startswith("__"):
        raise GeneratedCodePolicyError("Generated code cannot reference dunder attributes.")
    root_name = _attribute_root_name(node)
    if root_name in BLOCKED_MODULE_NAMES:
        raise GeneratedCodePolicyError(f"Generated code cannot reference {root_name!r}.")


def _validate_call(node: ast.Call) -> None:
    call_name = _call_name(node.func)
    if call_name in BLOCKED_CALL_NAMES:
        raise GeneratedCodePolicyError(f"Generated code cannot call {call_name!r}.")
    root_name = _attribute_root_name(node.func)
    if root_name in BLOCKED_MODULE_NAMES:
        raise GeneratedCodePolicyError(f"Generated code cannot call APIs on {root_name!r}.")
    if call_name == "circle":
        for keyword in node.keywords:
            if (
                keyword.arg == "subtract"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
            ):
                raise GeneratedCodePolicyError(
                    "Generated sketches cannot use subtract=True; create a separate solid and use Part.cut()."
                )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _attribute_root_name(node: ast.AST) -> str | None:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Call):
        return _attribute_root_name(current.func)
    if isinstance(current, ast.Name):
        return current.id
    return None


def _validate_sketch_profiles(tree: ast.Module) -> None:
    """Reject sketch call sequences that the live kernel cannot form into one wire."""
    sketch_calls: dict[str, list[str]] = {}

    for statement in tree.body:
        value: ast.AST | None = None
        assigned_name: str | None = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name):
                assigned_name = target.id
                value = statement.value
        elif isinstance(statement, ast.Expr):
            value = statement.value

        if value is None:
            continue

        root_name = _attribute_root_name(value)
        calls = [
            call_name
            for call in ast.walk(value)
            if isinstance(call, ast.Call)
            and (call_name := _call_name(call.func)) in {"arc", "circle", "line", "rect"}
        ]

        if assigned_name is not None and _contains_constructor(value, "Sketch"):
            sketch_calls[assigned_name] = calls
            _check_sketch_call_sequence(calls)
            continue

        if root_name in sketch_calls and calls:
            sketch_calls[root_name].extend(calls)
            _check_sketch_call_sequence(sketch_calls[root_name])


def _contains_constructor(node: ast.AST, constructor_name: str) -> bool:
    return any(
        isinstance(item, ast.Call)
        and isinstance(item.func, ast.Name)
        and item.func.id == constructor_name
        for item in ast.walk(node)
    )


def _check_sketch_call_sequence(calls: list[str]) -> None:
    closed_profiles = [name for name in calls if name in {"circle", "rect"}]
    if len(closed_profiles) > 1 or (closed_profiles and any(name in {"arc", "line"} for name in calls)):
        raise GeneratedCodePolicyError(
            "Each Sketch must contain exactly one connected profile; use separate sketches and Part booleans."
        )


def _execution_namespace() -> dict[str, Any]:
    safe_builtins = {
        "__import__": _safe_import,
        "False": False,
        "None": None,
        "True": True,
        "abs": abs,
        "max": max,
        "min": min,
        "round": round,
    }
    return {"__builtins__": safe_builtins, "__name__": "__main__"}


def _safe_import(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] | list[str] = (),
    level: int = 0,
) -> ModuleType:
    del globals, locals
    requested = set(fromlist)
    if level == 0 and name == "opencad" and requested <= ALLOWED_OPENCAD_IMPORTS:
        return importlib.import_module(name)
    raise ImportError("Generated code may only import Part and Sketch from opencad.")
