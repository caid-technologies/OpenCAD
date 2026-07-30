from __future__ import annotations

from pathlib import Path

from opencad import Part, Sketch, get_default_context, reset_default_context


def test_fluent_sketch_extrude_fillet_export(tmp_path: Path) -> None:
    reset_default_context()

    sketch = Sketch().rect(10, 20).circle(3, subtract=True)
    part = Part().extrude(sketch, depth=5).fillet(edges="top", radius=0.5)

    output = tmp_path / "output.step"
    part.export(str(output))

    ctx = get_default_context()
    assert output.exists()
    assert part.shape_id is not None
    assert sketch.feature_id is not None
    assert len(ctx.tree.nodes) >= 3  # root + sketch + feature chain


def test_fluent_boolean_chain_records_dependencies() -> None:
    reset_default_context()
    left = Part().box(10, 10, 10)
    right = Part().cylinder(3, 10)

    left.cut(right)

    ctx = get_default_context()
    assert left.feature_id is not None
    node = ctx.tree.nodes[left.feature_id]
    assert node.operation == "boolean_cut"
    assert len(node.depends_on) == 2


def test_fluent_sketch_writes_profile_order_metadata() -> None:
    reset_default_context()
    sketch = Sketch(name="Ordered").rect(4, 3).circle(1.0, center=(2.0, 1.5), subtract=True)
    Part().extrude(sketch, depth=2)

    ctx = get_default_context()
    assert sketch.feature_id is not None
    node = ctx.tree.nodes[sketch.feature_id]

    entities = node.parameters.get("entities", {})
    profile_order = node.parameters.get("profile_order", [])

    assert isinstance(entities, dict)
    assert isinstance(profile_order, list)
    assert len(profile_order) == len(entities)
    assert any(bool(v.get("subtract")) for v in entities.values() if v.get("type") == "circle")
