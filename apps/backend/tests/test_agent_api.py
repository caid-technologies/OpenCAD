from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import opencad_server.agent_router as agent_api
from opencad_agent.llm import LiteLlmProvider
from opencad_agent.generated_code import execute_generated_code
from opencad_agent.service import OpenCadAgentService
from opencad_server.agent_router import app
from opencad.tree.models import FeatureNode, FeatureTree


def _seed_tree() -> FeatureTree:
    return FeatureTree(
        root_id="root",
        nodes={
            "root": FeatureNode(
                id="root",
                name="Root",
                operation="seed",
                parameters={},
                depends_on=[],
                status="built",
                shape_id=None,
            )
        },
    )


def test_chat_api_can_return_generated_code(monkeypatch: pytest.MonkeyPatch) -> None:
    generated_code = (
        "from opencad import Part, Sketch\n"
        'cog = Part(name="LLM Cog").cylinder(radius=10, height=3, name="Cog")\n'
    )
    fake_service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(
            completion_func=lambda **_: {
                "choices": [{"message": {"content": generated_code}}]
            }
        ),
    )
    monkeypatch.setattr(agent_api, "_service", fake_service)
    client = TestClient(app)
    payload = {
        "message": "Build a cog",
        "tree_state": _seed_tree().model_dump(),
        "conversation_history": [],
        "llm_provider": "test",
        "llm_model": "model",
    }

    response = client.post("/chat", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert len(body["operations_executed"]) == 1
    assert body["generated_code"] == generated_code.strip()
    assert body["new_tree_state"]["root_id"] == "root"
    assert len(body["new_tree_state"]["nodes"]) > 1


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_concurrent_http_chats_keep_geometry_in_their_own_responses(monkeypatch):
    monkeypatch.setenv("OPENCAD_KERNEL_BACKEND", "analytic")
    entered, finished = Barrier(2, timeout=10), Barrier(2, timeout=10)

    def interleaved_execute(code):
        entered.wait()
        try:
            execute_generated_code(code)
        finally:
            finished.wait()

    monkeypatch.setattr(
        "opencad_agent.service.execute_generated_code", interleaved_execute
    )

    def completion(**kwargs):
        name = kwargs["messages"][-1]["content"]
        code = f'from opencad import Part\nPart().box(1, 1, 1, name="{name}")'
        return {"choices": [{"message": {"content": code}}]}

    provider = Mock(side_effect=completion)
    monkeypatch.setattr(
        agent_api,
        "_service",
        OpenCadAgentService(
            live_kernel=False, llm_client=LiteLlmProvider(completion_func=provider)
        ),
    )
    with TestClient(app) as client:

        def send(name):
            return client.post(
                "/chat",
                json={
                    "message": name,
                    "tree_state": _seed_tree().model_dump(),
                    "llm_model": "offline-test",
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(send, "http-A")
            second = pool.submit(send, "http-B")
            responses = [first.result(timeout=30), second.result(timeout=30)]

    assert provider.call_count == 2
    for name, response in zip(["http-A", "http-B"], responses):
        assert response.status_code == 200, response.text
        body = response.json()
        assert [n["name"] for n in body["new_tree_state"]["nodes"].values()] == [
            "Root",
            name,
        ]
        assert len(body["operations_executed"]) == 1
