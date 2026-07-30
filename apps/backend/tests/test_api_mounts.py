from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient


def _make_stub_package(name: str, endpoint: str) -> tuple[types.ModuleType, types.ModuleType]:
    package = types.ModuleType(name)
    api_module = types.ModuleType(f"{name}.api")

    router = APIRouter()

    @router.get(endpoint)
    def _stub() -> dict[str, str]:
        return {"module": name}

    api_module.router = router
    package.api = api_module
    return package, api_module


def test_backend_api_mounts_namespaced_routes(monkeypatch) -> None:
    stubs = {
        "opencad_kernel": _make_stub_package("opencad_kernel", "/healthz"),
        "opencad_agent": _make_stub_package("opencad_agent", "/chat"),
        "opencad_solver": _make_stub_package("opencad_solver", "/sketch/solve"),
        "opencad_tree": _make_stub_package("opencad_tree", "/trees"),
    }

    for package_name, (package_module, api_module) in stubs.items():
        monkeypatch.setitem(sys.modules, package_name, package_module)
        monkeypatch.setitem(sys.modules, f"{package_name}.api", api_module)

    api_path = Path(__file__).resolve().parents[1] / "api.py"
    spec = importlib.util.spec_from_file_location("backend_api_under_test", api_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    client = TestClient(module.app)
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200

    paths = openapi.json()["paths"]
    assert "/kernel/healthz" in paths
    assert "/agent/chat" in paths
    assert "/solver/sketch/solve" in paths
    assert "/tree/trees" in paths

    health = client.get("/")
    assert health.status_code == 200
    assert health.json() == {"status": "online", "engine": "OpenCAD"}
