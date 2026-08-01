from __future__ import annotations

from fastapi.testclient import TestClient

from opencad_server.kernel_router import app

def test_api_log_endpoint():
    client = TestClient(app)

    # Create a shape
    client.post("/operations/create_box", json={"payload": {"length": 2.0, "width": 3.0, "height": 4.0}})

    # Check log
    log_response = client.get("/operations/log")
    assert log_response.status_code == 200
    entries = log_response.json()
    assert len(entries) >= 1
    assert entries[-1]["operation"] == "create_box"
    assert entries[-1]["success"] is True


def test_api_replay_endpoint():
    client = TestClient(app)

    # Replay a sequence of operations
    replay_payload = {
        "entries": [
            {"operation": "create_box", "params": {"length": 10.0, "width": 5.0, "height": 3.0}},
            {"operation": "create_sphere", "params": {"radius": 2.5}},
        ]
    }
    response = client.post("/operations/replay", json=replay_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["replayed"] == 2
    assert len(data["results"]) == 2
    assert data["results"][0]["ok"] is True
    assert data["results"][1]["ok"] is True
    assert len(data["shape_ids"]) == 2


def test_api_replay_with_failure():
    client = TestClient(app)

    replay_payload = {
        "entries": [
            {"operation": "create_box", "params": {"length": -1.0, "width": 2.0, "height": 3.0}},
        ]
    }
    response = client.post("/operations/replay", json=replay_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["ok"] is False


def test_api_replay_with_stored_ids():
    """Replay endpoint should forward ids and produce matching shape_ids."""

    client = TestClient(app)
    replay_payload = {
        "entries": [
            {
                "id": "entry-aaa",
                "operation": "create_box",
                "params": {"length": 2, "width": 3, "height": 4},
                "result_shape_id": "shape-aaa",
            },
            {
                "id": "entry-bbb",
                "operation": "create_sphere",
                "params": {"radius": 1.5},
                "result_shape_id": "shape-bbb",
            },
        ]
    }
    response = client.post("/operations/replay", json=replay_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["shape_id"] == "shape-aaa"
    assert data["results"][1]["shape_id"] == "shape-bbb"
    assert set(data["shape_ids"]) == {"shape-aaa", "shape-bbb"}


def test_api_snapshot_endpoint():
    client = TestClient(app)
    # Create a shape first
    client.post("/operations/create_box", json={"payload": {"length": 1, "width": 1, "height": 1}})

    response = client.get("/snapshot")
    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["version"] == 1
    assert "created_at" in snapshot
    assert len(snapshot["entries"]) >= 1
    assert len(snapshot["shape_ids"]) >= 1
