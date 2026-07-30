from __future__ import annotations

import runpy
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

import opencad_agent.api as agent_api
from opencad_agent.api import app
from opencad_agent.generated_code import GeneratedCodePolicyError, validate_generated_code
from opencad_agent.llm import LiteLlmProvider
from opencad_agent.models import ChatRequest
from opencad_agent.planner import UnsupportedPromptError
from opencad_agent.prompting import build_code_generation_prompt, build_system_prompt
from opencad_agent.service import AgentConfigurationError, OpenCadAgentService
from opencad_agent.tools import ToolRuntime
from opencad_kernel.core.models import Success
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.registry import OperationRegistry
from opencad_tree.models import FeatureNode, FeatureTree

REPO_ROOT = Path(__file__).resolve().parents[3]


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


def test_system_prompt_contains_required_instructions() -> None:
    prompt = build_system_prompt(_seed_tree())
    assert "Current feature tree state (JSON)" in prompt
    assert "Available operations and their schemas" in prompt
    assert "always name features descriptively" in prompt
    assert "verify shapes exist and are not suppressed before referencing them" in prompt
    assert "plan the full sequence before executing" in prompt


def test_code_generation_prompt_contains_api_guidance() -> None:
    prompt = build_code_generation_prompt(_seed_tree())
    assert "Return only valid Python code." in prompt
    assert "from opencad import Part, Sketch" in prompt
    assert "Do not use filesystem" in prompt
    assert "Valid repeated-feature composition example" in prompt
    assert "Each Sketch variable may call exactly one" in prompt


def test_deterministic_planner_rejects_unknown_requests() -> None:
    service = OpenCadAgentService(live_kernel=False)
    with pytest.raises(UnsupportedPromptError, match="Enable Generate Code"):
        service.chat(
            ChatRequest(
                message="Build a cog",
                tree_state=_seed_tree(),
                generate_code=False,
            )
        )


def test_mounting_bracket_prompt_generates_minimum_operations() -> None:
    service = OpenCadAgentService()
    request = ChatRequest(
        message="Create a mounting bracket with 4 standoffs, a central cutout, and counterbored mounting ears",
        tree_state=_seed_tree(),
        conversation_history=[],
        reasoning=False,
    )

    response = service.chat(request)

    assert len(response.operations_executed) >= 8
    assert all(op.status == "ok" for op in response.operations_executed)

    node_ids = set(response.new_tree_state.nodes.keys())
    for op in response.operations_executed:
        if op.tool == "boolean_cut":
            assert str(op.arguments["base_id"]) in node_ids
            assert str(op.arguments["tool_id"]) in node_ids
        if op.tool == "fillet_edges":
            assert str(op.arguments["shape_id"]) in node_ids


def test_reasoning_toggle_changes_response_style() -> None:
    service = OpenCadAgentService()
    low = service.chat(
        ChatRequest(
            message="Create a mounting bracket with 4 standoffs, a central cutout, and counterbored mounting ears",
            tree_state=_seed_tree(),
            conversation_history=[],
            reasoning=False,
        )
    )
    high = service.chat(
        ChatRequest(
            message="Create a mounting bracket with 4 standoffs, a central cutout, and counterbored mounting ears",
            tree_state=_seed_tree(),
            conversation_history=[],
            reasoning=True,
        )
    )

    assert low.response != high.response
    assert "Plan:" in high.response


def test_chat_api_round_trip() -> None:
    client = TestClient(app)
    payload = {
        "message": "Create a mounting bracket with 4 standoffs, a central cutout, and counterbored mounting ears",
        "tree_state": _seed_tree().model_dump(),
        "conversation_history": [],
        "reasoning": True,
    }

    response = client.post("/chat", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert len(body["operations_executed"]) >= 8
    assert body["new_tree_state"]["root_id"] == "root"


def test_chat_api_can_return_generated_code(monkeypatch: pytest.MonkeyPatch) -> None:
    generated_code = (
        "from opencad import Part, Sketch\n"
        'cog = Part(name="LLM Cog").cylinder(radius=10, height=3, name="Cog")\n'
    )
    fake_service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(
            completion_func=lambda **_: {"choices": [{"message": {"content": generated_code}}]}
        ),
    )
    monkeypatch.setattr(agent_api, "_service", fake_service)
    client = TestClient(app)
    payload = {
        "message": "Build a cog",
        "tree_state": _seed_tree().model_dump(),
        "conversation_history": [],
        "reasoning": False,
        "llm_provider": "test",
        "llm_model": "model",
        "generate_code": True,
    }

    response = client.post("/chat", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert len(body["operations_executed"]) == 1
    assert body["generated_code"] == generated_code.strip()
    assert body["new_tree_state"]["root_id"] == "root"
    assert len(body["new_tree_state"]["nodes"]) > 1


def test_generated_code_policy_rejects_filesystem_imports() -> None:
    with pytest.raises(GeneratedCodePolicyError, match="only import Part and Sketch"):
        validate_generated_code("import os\nos.remove('part.step')\n")


def test_generated_code_policy_rejects_file_access() -> None:
    with pytest.raises(GeneratedCodePolicyError, match="'open'"):
        validate_generated_code("from opencad import Part, Sketch\nopen('part.step', 'w')\n")


def test_generated_code_policy_rejects_loops_before_execution() -> None:
    with pytest.raises(GeneratedCodePolicyError, match="For"):
        validate_generated_code("from opencad import Part, Sketch\nfor _ in range(10):\n    Part(name='Loop')\n")


def test_generated_code_policy_rejects_disconnected_sketch_profiles() -> None:
    code = """from opencad import Part, Sketch
profile = Sketch(name="Invalid")
profile.rect(10, 4)
profile.circle(2)
"""
    with pytest.raises(GeneratedCodePolicyError, match="exactly one connected profile"):
        validate_generated_code(code)


def test_generated_code_policy_rejects_subtract_flag() -> None:
    code = """from opencad import Part, Sketch
profile = Sketch(name="Invalid").circle(2, subtract=True)
"""
    with pytest.raises(GeneratedCodePolicyError, match="subtract=True"):
        validate_generated_code(code)


def test_service_surfaces_generated_code_policy_failures() -> None:
    service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(
            completion_func=lambda **_: {
                "choices": [{"message": {"content": "from opencad import Part, Sketch\nopen('part.step', 'w')"}}]
            }
        )
    )

    with pytest.raises(RuntimeError, match="Generated code validation failed"):
        service.chat(
            ChatRequest(
                message="Generate unsafe code",
                tree_state=_seed_tree(),
                conversation_history=[],
                reasoning=False,
                llm_model="test-model",
                generate_code=True,
            )
        )


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_planner_emits_line_entities_for_base_sketch() -> None:
    service = OpenCadAgentService()
    response = service.chat(
        ChatRequest(
            message="Create a mounting bracket with 4 standoffs, a central cutout, and counterbored mounting ears",
            tree_state=_seed_tree(),
            conversation_history=[],
            reasoning=False,
        )
    )

    add_sketch_ops = [op for op in response.operations_executed if op.tool == "add_sketch"]
    assert add_sketch_ops
    first = add_sketch_ops[0]
    entities = first.arguments["entities"]
    assert any(str(v.get("type", "")).lower() == "line" for v in entities.values())
    assert first.arguments.get("profile_order") == ["l1", "l2", "l3", "l4"]


def test_tool_runtime_supports_in_process_kernel_calls() -> None:
    kernel = OpenCadKernel(id_strategy="readable")
    registry = OperationRegistry(kernel)

    def kernel_call(operation: str, payload: dict[str, object]) -> dict[str, object]:
        result = registry.call(operation, payload)
        if isinstance(result, Success):
            return {"ok": True, "shape_id": result.shape_id}
        return {"ok": False, "message": result.message}

    runtime = ToolRuntime(_seed_tree(), kernel_call=kernel_call)
    sketch_id = runtime.add_sketch(
        name="Profile",
        entities={"p1": {"id": "p1", "type": "point", "x": 0.0, "y": 0.0}},
        constraints=[],
    )
    feature_id = runtime.extrude(sketch_id=sketch_id, depth=12.0, name="Base")

    tree = runtime.get_tree_state()
    shape_id = tree.nodes[feature_id].shape_id
    assert shape_id is not None
    assert not shape_id.startswith("shape-")
    assert shape_id.startswith("extrude-") or shape_id.startswith("box-")


def test_service_can_generate_code_with_litellm_provider() -> None:
    captured: dict[str, object] = {}
    expected_code = """from opencad import Part, Sketch

Part(name="LLM Part")"""

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "content": f"{expected_code}\n",
                    }
                }
            ]
        }

    service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(completion_func=fake_completion),
    )
    response = service.chat(
        ChatRequest(
            message="Generate a PCB carrier script",
            tree_state=_seed_tree(),
            conversation_history=[],
            reasoning=True,
            llm_provider="openai",
            llm_model="gpt-4o-mini",
            generate_code=True,
        )
    )

    assert response.operations_executed == []
    assert response.generated_code == expected_code
    assert captured["model"] == "openai/gpt-4o-mini"
    messages = captured["messages"]
    assert isinstance(messages, list)
    system_messages = [message for message in messages if message["role"] == "system"]
    assert system_messages
    assert any("Valid repeated-feature composition example" in message["content"] for message in system_messages)


def test_generate_code_requires_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCAD_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENCAD_LLM_MODEL", raising=False)
    service = OpenCadAgentService(live_kernel=False)

    with pytest.raises(AgentConfigurationError, match="requires an LLM"):
        service.chat(
            ChatRequest(
                message="Build a cog",
                tree_state=_seed_tree(),
                generate_code=True,
            )
        )


def test_chat_request_requires_model_when_provider_is_set() -> None:
    with pytest.raises(ValueError, match="llm_model is required"):
        ChatRequest(
            message="Generate a mounting bracket script",
            tree_state=_seed_tree(),
            conversation_history=[],
            llm_provider="openai",
            generate_code=True,
        )
