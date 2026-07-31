from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from opencad_tree.api import app
from opencad_tree.models import FeatureNode, FeatureTree
from opencad_tree.service import FeatureTreeService


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


def test_tree_api_crud_and_rebuild() -> None:
    client = TestClient(app)
    tree = _build_12_node_tree(root_id="api-root")

    create_response = client.post("/trees", json=tree.model_dump())
    assert create_response.status_code == 200

    edit_response = client.patch(
        "/trees/api-root/nodes/base",
        json={"parameters": {"height": 30}},
    )
    assert edit_response.status_code == 200

    rebuild_response = client.post("/trees/api-root/rebuild", json={"continue_on_error": False})
    assert rebuild_response.status_code == 200

    rebuilt = rebuild_response.json()
    assert rebuilt["nodes"]["mirror"]["status"] == "built"
    first_mirror_shape_id = rebuilt["nodes"]["mirror"]["shape_id"]

    second_edit = client.patch(
        "/trees/api-root/nodes/base",
        json={"parameters": {"height": 35}},
    )
    assert second_edit.status_code == 200
    second_rebuild = client.post("/trees/api-root/rebuild", json={"continue_on_error": False})
    assert second_rebuild.status_code == 200
    second_tree = second_rebuild.json()
    assert second_tree["nodes"]["mirror"]["shape_id"] != first_mirror_shape_id

    serialize_response = client.get("/trees/api-root/serialize")
    assert serialize_response.status_code == 200
    payload = serialize_response.json()["payload"]

    deserialize_response = client.post("/trees/deserialize", json={"payload": payload})
    assert deserialize_response.status_code == 200


def test_tree_healthz_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_tree_api_edits_solver_sketch_and_builds_kernel_segments() -> None:
    client = TestClient(app)
    tree = FeatureTree(
        root_id="sketch-edit-api",
        nodes={
            "sketch-edit-api": FeatureNode(
                id="sketch-edit-api",
                name="Bore Profile",
                operation="create_sketch",
                parameters={
                    "plane": "XY",
                    "origin": (0.0, 0.0, 0.0),
                    "entities": {"old": {"id": "old", "type": "circle", "center": (0.0, 0.0), "radius": 2.0}},
                    "constraints": [],
                    "profile_order": ["old"],
                },
                sketch_id="sketch-edit-api",
                shape_id="shape-old",
                status="built",
            ),
        },
    )
    assert client.post("/trees", json=tree.model_dump()).status_code == 200

    response = client.put(
        "/trees/sketch-edit-api/nodes/sketch-edit-api/sketch",
        json={
            "entities": {
                "bore": {"id": "bore", "type": "circle", "cx": 3.0, "cy": 4.0, "radius": 5.0},
            },
            "constraints": [],
        },
    )

    assert response.status_code == 200
    edited = response.json()["nodes"]["sketch-edit-api"]
    assert edited["status"] == "stale"
    assert edited["shape_id"] is None
    assert edited["parameters"]["entities"]["bore"]["cx"] == 3.0
    assert edited["parameters"]["profile_order"] == ["bore"]
    assert edited["parameters"]["segments"] == [
        {"type": "circle", "center": [3.0, 4.0], "radius": 5.0}
    ]


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


def test_tree_api_branch_and_solver_routes() -> None:
    client = TestClient(app)
    tree = FeatureTree(
        root_id="branch-api",
        nodes={
            "root": FeatureNode(id="root", name="Root", operation="sketch", sketch_id="sketch-api"),
            "extrude": FeatureNode(
                id="extrude",
                name="Extrude",
                operation="extrude",
                depends_on=["root"],
                parameter_bindings=[
                    {
                        "parameter": "height",
                        "source": "solver",
                        "source_key": "sketch-api",
                        "source_path": "entities.p1.y",
                        "cast_as": "float",
                    }
                ],
            ),
        },
    )

    create_response = client.post("/trees", json=tree.model_dump())
    assert create_response.status_code == 200

    branch_response = client.post(
        "/trees/branch-api/branches",
        json={"branch_name": "variant-b", "from_branch": "main"},
    )
    assert branch_response.status_code == 200

    switch_response = client.post("/trees/branch-api/branches/variant-b/switch")
    assert switch_response.status_code == 200
    assert switch_response.json()["active_branch"] == "variant-b"

    solver_response = client.post(
        "/trees/branch-api/solver/sketch-api",
        json={"solved_sketch": {"entities": {"p1": {"y": 88.0}}}},
    )
    assert solver_response.status_code == 200
    assert solver_response.json()["nodes"]["extrude"]["parameters"]["height"] == 88.0

    suppress_response = client.post(
        "/trees/branch-api/nodes/extrude/suppress",
        json={"suppressed": True},
    )
    assert suppress_response.status_code == 200
    assert suppress_response.json()["nodes"]["extrude"]["suppressed"] is True


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


def test_tree_snapshot_api_roundtrip() -> None:
    """Snapshot and restore should produce an identical tree."""
    client = TestClient(app)
    tree = _build_12_node_tree(root_id="snap-test")
    client.post("/trees", json=tree.model_dump())

    snap_response = client.get("/trees/snap-test/snapshot")
    assert snap_response.status_code == 200
    snapshot = snap_response.json()
    assert snapshot["version"] == 1
    assert "created_at" in snapshot

    restore_response = client.post("/trees/restore", json={"snapshot": snapshot})
    assert restore_response.status_code == 200
    restored = restore_response.json()
    assert set(restored["nodes"].keys()) == set(tree.nodes.keys())
    assert restored["root_id"] == "snap-test"
