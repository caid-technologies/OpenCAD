from __future__ import annotations

from fastapi.testclient import TestClient

from opencad_server.solver_router import app

def test_api_round_trip_mounting_bracket() -> None:
    client = TestClient(app)
    payload = {
        "entities": {
            "p1": {"id": "p1", "type": "point", "x": 0.0, "y": 0.0},
            "p2": {"id": "p2", "type": "point", "x": 40.0, "y": 0.8},
            "p3": {"id": "p3", "type": "point", "x": 39.2, "y": 20.0},
            "p4": {"id": "p4", "type": "point", "x": 0.5, "y": 20.4},
            "hole_center": {"id": "hole_center", "type": "point", "x": 10.0, "y": 10.0},
            "hole_edge": {"id": "hole_edge", "type": "point", "x": 13.0, "y": 10.0},
        },
        "constraints": [
            {"id": "f1", "type": "fixed", "a": "p1"},
            {"id": "h1", "type": "horizontal", "a": "p1", "b": "p2"},
            {"id": "v1", "type": "vertical", "a": "p2", "b": "p3"},
            {"id": "h2", "type": "horizontal", "a": "p3", "b": "p4"},
            {"id": "v2", "type": "vertical", "a": "p4", "b": "p1"},
            {"id": "d1", "type": "distance", "a": "p1", "b": "p2", "value": 40.0},
            {"id": "d2", "type": "distance", "a": "p2", "b": "p3", "value": 20.0},
            {"id": "hole", "type": "distance", "a": "hole_center", "b": "hole_edge", "value": 3.0},
        ],
    }

    response = client.post("/sketch/solve", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in {"SOLVED", "UNDERCONSTRAINED"}
    assert len(data["sketch"]["entities"]) == 6

    check_response = client.post("/sketch/check", json=data["sketch"])
    assert check_response.status_code == 200


def test_solver_healthz_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_diagnose_endpoint() -> None:
    client = TestClient(app)
    payload = {
        "entities": {
            "p1": {"id": "p1", "type": "point", "x": 0.0, "y": 0.0},
            "p2": {"id": "p2", "type": "point", "x": 1.0, "y": 0.0},
        },
        "constraints": [
            {"id": "f1", "type": "fixed", "a": "p1"},
            {"id": "dist", "type": "distance", "a": "p1", "b": "p2", "value": 1.0},
        ],
    }
    response = client.post("/sketch/diagnose", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "dof" in data
    assert "jacobian" in data
    assert "variables" in data
    assert "constraints" in data


def test_backend_info_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/backend")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert data["name"] in {"python", "solvespace"}
    assert "supports_3d" in data
    assert "solvespace_available" in data
