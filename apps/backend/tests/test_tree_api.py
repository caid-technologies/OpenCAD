from __future__ import annotations

from fastapi.testclient import TestClient

from opencad_server.tree_router import app
from opencad.tree.models import FeatureNode, FeatureTree


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
