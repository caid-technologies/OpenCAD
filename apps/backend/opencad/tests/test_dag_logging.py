from __future__ import annotations

from opencad import Part, Sketch, get_default_context, reset_default_context
from opencad_tree.service import FeatureTreeService


def test_each_headless_call_writes_feature_node() -> None:
    reset_default_context()

    sketch = Sketch(name="Profile").rect(8, 4)
    part = Part().extrude(sketch, depth=3, name="Base Extrude")
    part.offset(0.2, name="Offset")

    ctx = get_default_context()
    operations = [node.operation for node in ctx.tree.nodes.values() if node.id != ctx.tree.root_id]

    assert operations == ["create_sketch", "extrude", "offset_shape"]


def test_tree_round_trip_and_rebuild() -> None:
    reset_default_context()
    sketch = Sketch().rect(4, 4)
    Part().extrude(sketch, depth=2)

    ctx = get_default_context()
    payload = ctx.serialize_tree()

    restored = reset_default_context()
    restored.tree = FeatureTreeService.deserialize(payload)
    rebuilt = restored.rebuild_tree()

    assert rebuilt.root_id == "root"
    assert all(node.status in {"built", "suppressed"} for node in rebuilt.nodes.values())


def test_runtime_chat_executes_in_process() -> None:
    ctx = reset_default_context()
    response, operations = ctx.chat(
        "Create a mounting bracket with 4 standoffs, a central cutout, and counterbored mounting ears"
    )

    assert "bracket" in response.lower()
    assert len(operations) >= 8
    assert any(node.operation == "boolean_cut" for node in ctx.tree.nodes.values())
