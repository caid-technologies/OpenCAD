from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient

ROUTER_MODULES = {
    "kernel_router": "/healthz",
    "agent_router": "/chat",
    "solver_router": "/sketch/solve",
    "tree_router": "/trees",
}


def _make_stub_router_module(name: str, endpoint: str) -> types.ModuleType:
    module = types.ModuleType(f"opencad_server.{name}")
    router = APIRouter()

    @router.get(endpoint)
    def _stub() -> dict[str, str]:
        return {"module": name}

    module.router = router
    return module


def test_backend_api_mounts_namespaced_routes(monkeypatch) -> None:
    import opencad_server

    for name, endpoint in ROUTER_MODULES.items():
        stub = _make_stub_router_module(name, endpoint)
        monkeypatch.setitem(sys.modules, f"opencad_server.{name}", stub)
        monkeypatch.setattr(opencad_server, name, stub, raising=False)

    app_path = Path(opencad_server.__file__).resolve().parent / "app.py"
    spec = importlib.util.spec_from_file_location("backend_app_under_test", app_path)
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
