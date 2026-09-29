"""Regression coverage for shapes returned by the web agent (#38)."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from opencad.kernel.client import LocalKernelClient
from opencad.tree.models import FeatureTree
from opencad_agent.llm import LiteLlmProvider
from opencad_agent.tools import ToolRuntime
from opencad_server import agent_router, kernel_router, tree_router
from opencad_server.app import app


def test_default_web_clients_share_rendering_registry() -> None:
    """Default web services must never create geometry in private stores."""
    assert isinstance(agent_router._service.kernel_client, LocalKernelClient)
    assert agent_router._service.kernel_client.registry is kernel_router._REGISTRY
    assert isinstance(tree_router._KERNEL_CLIENT, LocalKernelClient)
    assert tree_router._KERNEL_CLIENT.registry is kernel_router._REGISTRY


def test_chat_shape_is_available_to_mesh_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate through the real web wiring and retrieve the resulting geometry."""
    if kernel_router._BACKEND_NAME != "occt":
        pytest.skip("Real mesh tessellation requires OCCT")
    code = 'from opencad import Part\nPart().box(30, 20, 2, name="PCB")'
    monkeypatch.setattr(agent_router._service, "llm_client", LiteLlmProvider(
        completion_func=lambda **_: {"choices": [{"message": {"content": code}}]}
    ))
    with TestClient(app) as client:
        response = client.post("/agent/chat", json={
            "message": "pcb", "llm_model": "offline-test",
            "tree_state": FeatureTree(root_id="root").model_dump(),
        })
        assert response.status_code == 200, response.text
        shape_id = response.json()["operations_executed"][-1]["result"]["shape_id"]
        mesh = client.get(f"/kernel/shapes/{shape_id}/mesh?deflection=0.1")
        assert mesh.status_code == 200, mesh.text
        assert mesh.json()["vertices"]
        assert mesh.json()["faces"]


@pytest.mark.parametrize("failure", [
    {"ok": False, "message": "Invalid cylinder"},
    {"ok": True},
    ConnectionError("Kernel unreachable"),
])
def test_live_tool_failure_never_creates_built_synthetic_shape(failure: object) -> None:
    """Rejected operations and transport errors must leave no fake feature."""
    client = Mock()
    if isinstance(failure, Exception):
        client.call_operation.side_effect = failure
    else:
        client.call_operation.return_value = failure
    runtime = ToolRuntime(FeatureTree(root_id="root"), kernel_client=client)
    with pytest.raises(RuntimeError, match="Kernel operation"):
        runtime.add_cylinder({"x": 0, "y": 0, "z": 0}, 1, 2, "Cylinder")
    assert list(runtime.tree.nodes) == ["root"]


def test_rebuilt_tree_shape_is_available_to_mesh_endpoint() -> None:
    """Tree edits must create replacement geometry in the rendering store."""
    if kernel_router._BACKEND_NAME != "occt":
        pytest.skip("Real mesh tessellation requires OCCT")
    with TestClient(app) as client:
        tree = {"root_id": "mesh-regression", "nodes": {"mesh-regression": {
            "id": "mesh-regression", "name": "Board", "operation": "create_box",
            "parameters": {"length": 30, "width": 20, "height": 2},
        }}}
        assert client.post("/tree/trees", json=tree).status_code == 200
        rebuilt = client.post("/tree/trees/mesh-regression/rebuild", json={})
        assert rebuilt.status_code == 200, rebuilt.text
        node = rebuilt.json()["nodes"]["mesh-regression"]
        assert node["status"] == "built", node
        response = client.get(f"/kernel/shapes/{node['shape_id']}/mesh")
        assert response.status_code == 200, response.text
        assert response.json()["vertices"]


def test_chat_kernel_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected live operation must not be returned as a successful chat."""
    code = 'from opencad import Part\nPart().box(30, 20, 2, name="PCB")'
    monkeypatch.setattr(agent_router._service, "llm_client", LiteLlmProvider(
        completion_func=lambda **_: {"choices": [{"message": {"content": code}}]}
    ))
    client = Mock()
    client.call_operation.return_value = {"ok": False, "message": "Kernel rejected geometry"}
    monkeypatch.setattr(agent_router._service, "kernel_client", client)
    response = TestClient(app).post("/agent/chat", json={
        "message": "pcb", "llm_model": "offline-test",
        "tree_state": FeatureTree(root_id="root").model_dump(),
    })
    assert response.status_code == 422, response.text
    assert "Kernel rejected geometry" in response.json()["detail"]
