from __future__ import annotations

from fastapi.testclient import TestClient

from opencad_server.kernel_router import app

class TestTopologyAPI:
    def test_get_topology_endpoint(self) -> None:
        client = TestClient(app)
        # Create a box
        resp = client.post("/operations/create_box", json={"payload": {"length": 5, "width": 5, "height": 5}})
        assert resp.status_code == 200
        shape_id = resp.json()["shape_id"]

        # Get topology
        topo_resp = client.get(f"/shapes/{shape_id}/topology")
        assert topo_resp.status_code == 200
        topo = topo_resp.json()
        assert topo["shape_id"] == shape_id
        assert len(topo["faces"]) > 0

    def test_get_faces_endpoint(self) -> None:
        client = TestClient(app)
        resp = client.post("/operations/create_box", json={"payload": {"length": 5, "width": 5, "height": 5}})
        shape_id = resp.json()["shape_id"]

        faces_resp = client.get(f"/shapes/{shape_id}/faces")
        assert faces_resp.status_code == 200
        faces = faces_resp.json()
        assert len(faces) == 6

    def test_select_endpoint(self) -> None:
        client = TestClient(app)
        resp = client.post("/operations/create_box", json={"payload": {"length": 5, "width": 5, "height": 5}})
        shape_id = resp.json()["shape_id"]

        sel_resp = client.post(f"/shapes/{shape_id}/select", json={
            "kind": "face", "tags": ["top"],
        })
        assert sel_resp.status_code == 200
        results = sel_resp.json()
        assert len(results) == 1
        assert "top" in results[0]["tags"]

    def test_topology_not_found(self) -> None:
        client = TestClient(app)
        resp = client.get("/shapes/nonexistent/topology")
        assert resp.status_code == 404
