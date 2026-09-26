from __future__ import annotations

import json

import pytest

from opencad.assembly import (
    AssemblyComponent,
    AssemblyTree,
    deserialize_assembly_tree,
    import_assembly_tree,
    serialize_assembly_tree,
)


def _micro_arm() -> AssemblyTree:
    return AssemblyTree(
        id="micro-arm",
        name="Micro Arm",
        root_ids=["micro-arm"],
        components={
            "micro-arm": AssemblyComponent(
                id="micro-arm",
                name="Micro Arm",
                child_ids=["base", "shoulder"],
            ),
            "base": AssemblyComponent(
                id="base",
                name="Base",
                geometry_refs=["shape-base"],
            ),
            "shoulder": AssemblyComponent(
                id="shoulder",
                name="Shoulder",
                child_ids=["servo", "upper-arm"],
            ),
            "servo": AssemblyComponent(
                id="servo",
                name="Servo",
                geometry_refs=["shape-servo"],
            ),
            "upper-arm": AssemblyComponent(
                id="upper-arm",
                name="Upper Arm",
                geometry_refs=["shape-upper-arm"],
                feature_refs=["extrude-19"],
                metadata={"source_id": "link_upper_arm"},
            ),
        },
    )


def test_nested_assembly_resolves_descendants_and_geometry() -> None:
    tree = _micro_arm()

    assert tree.descendant_ids("shoulder") == ["shoulder", "servo", "upper-arm"]
    assert tree.geometry_refs_for("shoulder") == [
        "shape-servo",
        "shape-upper-arm",
    ]
    assert tree.geometry_refs_for("shoulder", include_descendants=False) == []


def test_geometry_regeneration_preserves_semantic_component_id() -> None:
    tree = _micro_arm()
    regenerated = tree.replace_component_geometry("upper-arm", ["shape-42"])

    assert regenerated.components["upper-arm"].id == "upper-arm"
    assert regenerated.components["upper-arm"].geometry_refs == ["shape-42"]
    assert tree.components["upper-arm"].geometry_refs == ["shape-upper-arm"]


def test_versioned_serialization_roundtrip() -> None:
    tree = _micro_arm()
    payload = serialize_assembly_tree(tree)
    restored = deserialize_assembly_tree(payload)

    assert restored == tree
    assert json.loads(payload)["version"] == 1


def test_import_boundary_accepts_raw_mapping_and_snapshot_json() -> None:
    tree = _micro_arm()

    raw_import = import_assembly_tree(tree.model_dump())
    snapshot_import = import_assembly_tree(serialize_assembly_tree(tree))

    assert raw_import == tree
    assert snapshot_import == tree


def test_rejects_missing_child() -> None:
    with pytest.raises(ValueError, match="missing child"):
        AssemblyTree(
            id="bad",
            name="Bad",
            root_ids=["root"],
            components={
                "root": AssemblyComponent(
                    id="root",
                    name="Root",
                    child_ids=["missing"],
                )
            },
        )


def test_rejects_multiple_parents() -> None:
    with pytest.raises(ValueError, match="multiple parents"):
        AssemblyTree(
            id="bad",
            name="Bad",
            root_ids=["a", "b"],
            components={
                "a": AssemblyComponent(id="a", name="A", child_ids=["child"]),
                "b": AssemblyComponent(id="b", name="B", child_ids=["child"]),
                "child": AssemblyComponent(id="child", name="Child"),
            },
        )


def test_rejects_cycles() -> None:
    with pytest.raises(ValueError, match="cycle"):
        AssemblyTree(
            id="bad",
            name="Bad",
            root_ids=[],
            components={
                "a": AssemblyComponent(id="a", name="A", child_ids=["b"]),
                "b": AssemblyComponent(id="b", name="B", child_ids=["a"]),
            },
        )


def test_roots_must_match_parentless_components() -> None:
    with pytest.raises(ValueError, match="root IDs"):
        AssemblyTree(
            id="bad",
            name="Bad",
            root_ids=["child"],
            components={
                "root": AssemblyComponent(id="root", name="Root", child_ids=["child"]),
                "child": AssemblyComponent(id="child", name="Child"),
            },
        )
