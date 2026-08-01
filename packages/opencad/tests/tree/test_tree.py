from __future__ import annotations

import json

import pytest

from opencad.tree.models import FeatureNode, FeatureTree
from opencad.tree.service import FeatureTreeService


def _build_12_node_tree(root_id: str = "base") -> FeatureTree:
    nodes = {
        "base": FeatureNode(id="base", name="Base", operation="extrude", parameters={"height": 10}),
        "frame": FeatureNode(
            id="frame",
            name="Frame",
            operation="boolean_union",
            parameters={"thickness": 2},
            depends_on=["base"],
        ),
        "rib1": FeatureNode(id="rib1", name="Rib1", operation="extrude", depends_on=["frame"]),
        "rib2": FeatureNode(id="rib2", name="Rib2", operation="extrude", depends_on=["frame"]),
        "pocket": FeatureNode(id="pocket", name="Pocket", operation="boolean_cut", depends_on=["frame"]),
        "boss1": FeatureNode(id="boss1", name="Boss1", operation="extrude", depends_on=["rib1"]),
        "boss2": FeatureNode(id="boss2", name="Boss2", operation="extrude", depends_on=["rib2"]),
        "hole1": FeatureNode(id="hole1", name="Hole1", operation="boolean_cut", depends_on=["boss1"]),
        "hole2": FeatureNode(id="hole2", name="Hole2", operation="boolean_cut", depends_on=["boss2"]),
        "fillet": FeatureNode(
            id="fillet",
            name="Fillet",
            operation="fillet",
            depends_on=["pocket", "hole1", "hole2"],
        ),
        "chamfer": FeatureNode(id="chamfer", name="Chamfer", operation="chamfer", depends_on=["fillet"]),
        "mirror": FeatureNode(id="mirror", name="Mirror", operation="mirror", depends_on=["chamfer"]),
    }
    return FeatureTree(nodes=nodes, root_id=root_id)


def _kernel_client(node: FeatureNode, tree: FeatureTree) -> str:
    parent_shapes = tuple((tree.nodes[parent].shape_id or "none") for parent in sorted(node.depends_on))
    params = json.dumps(node.parameters, sort_keys=True, default=str)
    digest = abs(hash((node.operation, params, parent_shapes))) % 1_000_000
    return f"shape-{node.id}-{digest}"


def test_12_node_tree_rebuild_sets_shape_ids() -> None:
    tree = _build_12_node_tree()
    rebuilt = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)

    assert len(rebuilt.nodes) == 12
    for node in rebuilt.nodes.values():
        assert node.status == "built"
        assert node.shape_id is not None


def test_edit_base_marks_all_descendants_stale() -> None:
    tree = _build_12_node_tree()
    built = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)
    edited = FeatureTreeService.edit_feature(built, "base", {"height": 15})

    for node_id, node in edited.nodes.items():
        assert node.status == "stale"
        assert node.shape_id is None
        assert node_id in edited.nodes


def test_rebuild_after_edit_changes_downstream_shape_ids() -> None:
    tree = _build_12_node_tree()
    initial = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)
    before = {node_id: node.shape_id for node_id, node in initial.nodes.items()}

    edited = FeatureTreeService.edit_feature(initial, "base", {"height": 25})
    rebuilt = FeatureTreeService.rebuild(edited, kernel_client=_kernel_client)
    after = {node_id: node.shape_id for node_id, node in rebuilt.nodes.items()}

    assert rebuilt.nodes["base"].status == "built"
    assert before["base"] != after["base"]
    assert before["mirror"] != after["mirror"]


def test_circular_dependency_detection() -> None:
    tree = _build_12_node_tree()
    tree.nodes["base"].depends_on = ["mirror"]

    with pytest.raises(ValueError, match="Circular dependency"):
        FeatureTreeService.ensure_acyclic(tree)


def test_serialization_roundtrip() -> None:
    tree = _build_12_node_tree()
    payload = FeatureTreeService.serialize(tree)
    restored = FeatureTreeService.deserialize(payload)

    assert restored.root_id == tree.root_id
    assert set(restored.nodes.keys()) == set(tree.nodes.keys())


def test_sketch_reference_is_a_dependency_but_not_body_parent() -> None:
    node = FeatureNode(
        id="extrude",
        name="Extrude",
        operation="extrude",
        sketch_id="profile",
    )

    assert node.parent_id is None
    assert node.tool_refs == []
    assert node.depends_on == ["profile"]


def test_legacy_sketch_parent_is_migrated_to_profile_dependency() -> None:
    node = FeatureNode.model_validate({
        "id": "extrude",
        "name": "Extrude",
        "operation": "extrude",
        "sketch_id": "profile",
        "parent_id": "profile",
        "tool_refs": [],
        "depends_on": ["profile"],
    })

    assert node.parent_id is None
    assert node.depends_on == ["profile"]


def test_editing_separate_sketch_stales_consuming_component() -> None:
    tree = FeatureTree(
        root_id="profile",
        nodes={
            "profile": FeatureNode(
                id="profile",
                name="Profile",
                operation="create_sketch",
                sketch_id="profile",
                status="built",
                shape_id="shape-profile",
            ),
            "extrude": FeatureNode(
                id="extrude",
                name="Body",
                operation="extrude",
                sketch_id="profile",
                status="built",
                shape_id="shape-body",
            ),
        },
    )

    updated = FeatureTreeService.edit_feature(tree, "profile", {"segments": []})

    assert updated.nodes["profile"].status == "stale"
    assert updated.nodes["extrude"].status == "stale"
    assert updated.nodes["extrude"].parent_id is None


def test_delete_with_dependents_errors() -> None:
    tree = _build_12_node_tree()
    with pytest.raises(ValueError, match="dependents"):
        FeatureTreeService.delete_feature(tree, "frame")


def test_delete_leaf_node() -> None:
    tree = _build_12_node_tree()
    updated = FeatureTreeService.delete_feature(tree, "mirror")
    assert "mirror" not in updated.nodes
    assert len(updated.nodes) == 11


def test_missing_dependency_rejected() -> None:
    tree = _build_12_node_tree()
    tree.nodes["rib1"].depends_on = ["does-not-exist"]

    with pytest.raises(ValueError, match="missing parent"):
        FeatureTreeService.ensure_acyclic(tree)


def test_suppress_feature_blocks_branch_rebuild() -> None:
    tree = _build_12_node_tree()
    built = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)

    suppressed = FeatureTreeService.suppress_feature(built, "fillet", suppressed=True)
    rebuilt = FeatureTreeService.rebuild(suppressed, kernel_client=_kernel_client)

    assert rebuilt.nodes["fillet"].status == "suppressed"
    assert rebuilt.nodes["fillet"].suppressed is True
    assert rebuilt.nodes["fillet"].shape_id is None
    # Descendants are transitively suppressed, not merely stale.
    assert rebuilt.nodes["chamfer"].status == "suppressed"
    assert rebuilt.nodes["chamfer"].suppressed is True
    assert rebuilt.nodes["mirror"].status == "suppressed"
    assert rebuilt.nodes["mirror"].suppressed is True


def test_branch_switch_keeps_independent_parameter_variants() -> None:
    tree = _build_12_node_tree()
    tree = FeatureTreeService.create_branch(tree, "alt-loft")
    alt = FeatureTreeService.switch_branch(tree, "alt-loft")
    alt = FeatureTreeService.edit_feature(alt, "base", {"height": 123})

    main = FeatureTreeService.switch_branch(alt, "main")
    assert main.nodes["base"].parameters["height"] == 10

    roundtrip_alt = FeatureTreeService.switch_branch(main, "alt-loft")
    assert roundtrip_alt.nodes["base"].parameters["height"] == 123


def test_solver_result_updates_bound_parameters_and_stales_subgraph() -> None:
    tree = FeatureTree(
        root_id="root",
        nodes={
            "root": FeatureNode(id="root", name="Root", operation="sketch", sketch_id="sketch-1"),
            "extrude": FeatureNode(
                id="extrude",
                name="Extrude",
                operation="extrude",
                depends_on=["root"],
                parameters={"height": 10.0},
                parameter_bindings=[
                    {
                        "parameter": "height",
                        "source": "solver",
                        "source_key": "sketch-1",
                        "source_path": "entities.p1.y",
                        "cast_as": "float",
                    }
                ],
            ),
        },
    )

    built = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)
    updated = FeatureTreeService.apply_solver_result(
        built,
        sketch_id="sketch-1",
        solved_sketch={"entities": {"p1": {"x": 0.0, "y": 42.5}}},
    )

    assert updated.nodes["extrude"].parameters["height"] == pytest.approx(42.5)
    assert updated.nodes["extrude"].status == "stale"


def test_set_typed_parameters_marks_downstream_stale() -> None:
    tree = _build_12_node_tree()
    built = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)
    updated = FeatureTreeService.set_typed_parameters(
        built,
        node_id="base",
        typed_parameters={"height": {"type": "float", "value": 55.0}},
    )

    assert updated.nodes["base"].typed_parameters["height"].type == "float"
    assert updated.nodes["base"].typed_parameters["height"].value == 55.0
    assert updated.nodes["base"].status == "stale"
    assert updated.nodes["mirror"].status == "stale"


# ── Transitive suppression tests ────────────────────────────────────


def test_transitive_suppression_marks_all_descendants() -> None:
    """Suppressing a mid-tree node must set suppressed=True on every descendant."""
    tree = _build_12_node_tree()
    built = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)

    suppressed = FeatureTreeService.suppress_feature(built, "frame", suppressed=True)

    # frame and all its descendants are suppressed
    for node_id in ["frame", "rib1", "rib2", "pocket", "boss1", "boss2",
                     "hole1", "hole2", "fillet", "chamfer", "mirror"]:
        node = suppressed.nodes[node_id]
        assert node.suppressed is True, f"{node_id} should be suppressed"
        assert node.status == "suppressed", f"{node_id} status should be 'suppressed'"
        assert node.shape_id is None, f"{node_id} shape_id should be cleared"

    # base is untouched
    assert suppressed.nodes["base"].suppressed is False
    assert suppressed.nodes["base"].status == "built"


def test_unsuppress_restores_descendants_to_stale() -> None:
    """Unsuppressing must clear suppressed flag on descendants and set status to stale."""
    tree = _build_12_node_tree()
    built = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)

    suppressed = FeatureTreeService.suppress_feature(built, "frame", suppressed=True)
    unsuppressed = FeatureTreeService.suppress_feature(suppressed, "frame", suppressed=False)

    for node_id in ["frame", "rib1", "rib2", "pocket", "boss1", "boss2",
                     "hole1", "hole2", "fillet", "chamfer", "mirror"]:
        node = unsuppressed.nodes[node_id]
        assert node.suppressed is False, f"{node_id} should not be suppressed"
        assert node.status == "stale", f"{node_id} status should be 'stale'"

    # Rebuild should recover all nodes.
    rebuilt = FeatureTreeService.rebuild(unsuppressed, kernel_client=_kernel_client)
    for node in rebuilt.nodes.values():
        assert node.status == "built"


def test_rebuild_skips_transitively_suppressed_nodes() -> None:
    """Rebuild must leave transitively suppressed descendants in suppressed state."""
    tree = _build_12_node_tree()
    suppressed = FeatureTreeService.suppress_feature(tree, "rib1", suppressed=True)
    rebuilt = FeatureTreeService.rebuild(suppressed, kernel_client=_kernel_client)

    assert rebuilt.nodes["rib1"].status == "suppressed"
    assert rebuilt.nodes["boss1"].status == "suppressed"
    assert rebuilt.nodes["hole1"].status == "suppressed"

    # Siblings should still build.
    assert rebuilt.nodes["rib2"].status == "built"
    assert rebuilt.nodes["boss2"].status == "built"

    # fillet depends on hole1 (suppressed), so it should be stale.
    assert rebuilt.nodes["fillet"].status == "stale"


# ── Expression evaluator tests ──────────────────────────────────────


def test_expression_binding_evaluated_at_rebuild() -> None:
    """An expression binding should compute the value at rebuild time."""
    tree = FeatureTree(
        root_id="root",
        nodes={
            "root": FeatureNode(
                id="root", name="Root", operation="seed",
                parameters={"width": 10.0},
                status="built",
            ),
            "extrude": FeatureNode(
                id="extrude", name="Extrude", operation="extrude",
                depends_on=["root"],
                parameters={"height": 0.0, "width": 0.0},
                parameter_bindings=[
                    {
                        "parameter": "height",
                        "source": "node",
                        "source_key": "root",
                        "source_path": "parameters.width",
                        "expression": "width * 2 + 5",
                        "cast_as": "float",
                    }
                ],
            ),
        },
    )

    rebuilt = FeatureTreeService.rebuild(tree, kernel_client=_kernel_client)
    # width from root is 10.0, expression: width * 2 + 5 = 25
    assert rebuilt.nodes["extrude"].parameters["height"] == pytest.approx(25.0)
    assert rebuilt.nodes["extrude"].status == "built"


# ── Snapshot roundtrip tests ────────────────────────────────────────


