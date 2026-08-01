"""Enforce the core/backend separation.

The core distributions (``packages/opencad`` and ``packages/opencad-agent``)
hold geometry, solving, tree, and agent logic. They ship without a web stack,
so they may not depend on the HTTP transport layer (``opencad_server``) or on
any web/network library. All FastAPI routing and all outbound HTTP lives in
``apps/backend``.

This test locates the core packages through their installed modules, so it
works from a workspace checkout and from an installed environment alike.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Top-level roots only. The scan recurses, so opencad.kernel, opencad.solver,
# and opencad.tree are covered by walking `opencad`.
CORE_PACKAGES = (
    "opencad",
    "opencad_agent",
)

FORBIDDEN_ROOTS = frozenset(
    {
        "fastapi",
        "starlette",
        "httpx",
        "uvicorn",
        "sse_starlette",
        "dotenv",
        "opencad_server",
    }
)


def _core_modules() -> list[tuple[str, Path]]:
    """Every non-test source file in the core packages, labelled for test IDs."""
    import importlib

    modules: list[tuple[str, Path]] = []
    for package_name in CORE_PACKAGES:
        package = importlib.import_module(package_name)
        root = Path(package.__file__).resolve().parent
        for path in sorted(root.rglob("*.py")):
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            modules.append((f"{package_name}/{path.relative_to(root)}", path))
    return modules


def _imported_roots(path: Path) -> set[str]:
    """Collect the top-level name of every import in a module, at any nesting."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_core_module_set_is_discovered() -> None:
    """Guard against the scan silently matching nothing."""
    assert len(_core_modules()) > 20


@pytest.mark.parametrize("label,path", _core_modules(), ids=[label for label, _ in _core_modules()])
def test_core_module_has_no_web_dependency(label: str, path: Path) -> None:
    leaked = sorted(_imported_roots(path) & FORBIDDEN_ROOTS)
    assert not leaked, (
        f"{label} imports {leaked}. Core packages must stay transport-agnostic — "
        "move HTTP concerns into apps/backend and inject a KernelClient instead."
    )
