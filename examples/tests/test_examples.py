"""
Tests that validate the headless example scripts run end-to-end.

These are integration-style checks for examples/01_hello_part and
examples/02_parametric_bracket.  They import and call each example's
``main()`` function directly, then assert on the resulting state.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

from opencad import get_default_context, reset_default_context

# Resolve example paths relative to this file
_EXAMPLES = Path(__file__).parent.parent


def _load_example(rel_path: str):
    """Import a module from an examples sub-directory."""
    mod_path = _EXAMPLES / rel_path
    spec = importlib.util.spec_from_file_location("_example", mod_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Example 01 ───────────────────────────────────────────────────────────────

class TestHelloPart:
    def test_feature_tree_built(self) -> None:
        """hello_part.py should produce a tree with at least 5 nodes."""
        reset_default_context()
        mod = _load_example("01_hello_part/hello_part.py")
        mod.main()

        ctx = get_default_context()
        assert len(ctx.tree.nodes) >= 5  # root + box + cyl + cut + fillet

    def test_step_export_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """hello_part.py should write a non-empty STEP file."""
        reset_default_context()
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        mod = _load_example("01_hello_part/hello_part.py")
        mod.main()

        step_path = tmp_path / "hello_part.step"
        json_path = tmp_path / "hello_part_tree.json"
        assert step_path.exists()
        assert step_path.stat().st_size > 0
        assert json_path.exists()

    def test_operations_in_tree(self) -> None:
        """The tree should contain box, cylinder, boolean_cut, fillet_edges nodes."""
        reset_default_context()
        mod = _load_example("01_hello_part/hello_part.py")
        mod.main()

        ctx = get_default_context()
        operations = {n.operation for n in ctx.tree.nodes.values()}
        assert "create_box" in operations
        assert "create_cylinder" in operations
        assert "boolean_cut" in operations
        assert "fillet_edges" in operations


# ── Example 02 ───────────────────────────────────────────────────────────────

class TestParametricBracket:
    def test_feature_tree_built(self) -> None:
        """bracket.py should produce a tree with at least 7 nodes."""
        reset_default_context()
        mod = _load_example("02_parametric_bracket/bracket.py")
        mod.main()

        ctx = get_default_context()
        assert len(ctx.tree.nodes) >= 7  # root + sketch + extrude + cyl + cut + pattern + fillet

    def test_expected_operations(self) -> None:
        """The feature tree should contain the full modeling sequence."""
        reset_default_context()
        mod = _load_example("02_parametric_bracket/bracket.py")
        mod.main()

        ctx = get_default_context()
        operations = {n.operation for n in ctx.tree.nodes.values()}
        assert "create_sketch" in operations
        assert "extrude" in operations
        assert "create_cylinder" in operations
        assert "boolean_cut" in operations
        assert "linear_pattern" in operations
        assert "fillet_edges" in operations

    def test_all_nodes_built(self) -> None:
        """Every node in the tree should reach 'built' status."""
        reset_default_context()
        mod = _load_example("02_parametric_bracket/bracket.py")
        mod.main()

        ctx = get_default_context()
        for node in ctx.tree.nodes.values():
            assert node.status == "built", (
                f"Node {node.id} (op={node.operation}) has status={node.status!r}"
            )

    def test_design_parameters_respected(self) -> None:
        """Linear pattern count and fillet radius should reflect the design parameters."""
        reset_default_context()
        mod = _load_example("02_parametric_bracket/bracket.py")
        mod.main()

        ctx = get_default_context()
        pattern_nodes = [
            n for n in ctx.tree.nodes.values() if n.operation == "linear_pattern"
        ]
        assert pattern_nodes, "Expected at least one linear_pattern node"
        count = pattern_nodes[0].parameters.get("count")
        assert count == mod.HOLE_COUNT

        fillet_nodes = [
            n for n in ctx.tree.nodes.values() if n.operation == "fillet_edges"
        ]
        assert fillet_nodes, "Expected at least one fillet_edges node"
        radius = fillet_nodes[0].parameters.get("radius")
        assert radius == pytest.approx(mod.FILLET_R)
