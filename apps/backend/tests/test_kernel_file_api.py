from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import opencad_server.kernel_router as kernel_api
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.registry import OperationRegistry


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    kernel = OpenCadKernel(tolerance=1e-6, id_strategy="readable")
    monkeypatch.setattr(kernel_api, "_KERNEL", kernel)
    monkeypatch.setattr(kernel_api, "_REGISTRY", OperationRegistry(kernel))
    return TestClient(kernel_api.app)


@pytest.mark.parametrize("file_format", ["step", "stp", "stl"])
def test_browser_export_import_roundtrip(client: TestClient, file_format: str) -> None:
    created = client.post(
        "/operations/create_box",
        json={"payload": {"length": 4.0, "width": 3.0, "height": 2.0}},
    )
    assert created.status_code == 200
    shape_id = created.json()["shape_id"]

    exported = client.get(
        f"/files/{shape_id}/export",
        params={"format": file_format, "filename": f"bracket.{file_format}"},
    )
    assert exported.status_code == 200
    assert f'filename="bracket.{file_format}"' in exported.headers["content-disposition"]

    imported = client.post(
        "/files/import",
        params={"filename": f"bracket.{file_format}"},
        content=exported.content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert imported.status_code == 200
    assert imported.json()["format"] == file_format
    assert imported.json()["shape_id"]


def test_browser_import_rejects_unsupported_format(client: TestClient) -> None:
    response = client.post(
        "/files/import",
        params={"filename": "part.obj"},
        content=b"not an obj",
    )
    assert response.status_code == 415


def test_browser_export_reports_missing_shape(client: TestClient) -> None:
    response = client.get("/files/missing/export", params={"format": "stl"})
    assert response.status_code == 404
