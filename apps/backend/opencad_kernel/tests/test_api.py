from __future__ import annotations

from fastapi.testclient import TestClient

from opencad_kernel.api import app


def test_kernel_healthz() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "backend" in data


def test_kernel_operations_list_and_schema() -> None:
    client = TestClient(app)
    ops_response = client.get("/operations")
    assert ops_response.status_code == 200
    ops = ops_response.json()
    assert "create_box" in ops

    schema_response = client.get("/operations/create_box/schema")
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert "properties" in schema
    assert "length" in schema["properties"]


def test_kernel_operation_call_validation() -> None:
    client = TestClient(app)
    missing_field = client.post("/operations/create_box", json={"payload": {"length": 1.0, "width": 2.0}})
    assert missing_field.status_code == 200
    assert missing_field.json()["ok"] is False
    assert missing_field.json()["failed_check"] == "schema_validation"

    unknown_op = client.post("/operations/nope", json={"payload": {}})
    assert unknown_op.status_code == 200
    assert unknown_op.json()["ok"] is False
    assert unknown_op.json()["failed_check"] == "operation_lookup"
