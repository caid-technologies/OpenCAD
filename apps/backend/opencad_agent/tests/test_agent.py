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
from opencad_agent.prompting import build_code_generation_prompt, build_system_prompt
from opencad_agent.service import AgentConfigurationError, OpenCadAgentService
from opencad_agent.tools import ToolRuntime, _kernel_operation_url
from opencad_kernel.core.models import Success
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.registry import OperationRegistry
from opencad_tree.models import FeatureNode, FeatureTree

REPO_ROOT = Path(__file__).resolve().parents[4]


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


def test_kernel_operation_url_does_not_duplicate_gateway_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("opencad_agent.tools._KERNEL_URL", "http://127.0.0.1:8000/kernel")
    assert _kernel_operation_url("create_cylinder") == "http://127.0.0.1:8000/kernel/operations/create_cylinder"


def test_kernel_operation_url_adds_gateway_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("opencad_agent.tools._KERNEL_URL", "http://127.0.0.1:8000")
    assert _kernel_operation_url("create_cylinder") == "http://127.0.0.1:8000/kernel/operations/create_cylinder"


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
    assert "Valid screw composition example" in prompt
    assert "Never boolean disconnected solids" in prompt
    assert "Each Sketch variable may call exactly one" in prompt
    for primitive in ("box", "cylinder", "sphere", "cone", "torus"):
        assert f".{primitive}(" in prompt
    assert "A torus must use `Part(name=...).torus" in prompt


def test_chat_executes_native_torus_primitive() -> None:
    generated_code = (
        "from opencad import Part, Sketch\n"
        'result = Part(name="Torus").torus('
        'major_radius=30, minor_radius=10, name="Torus")\n'
    )
    service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(
            completion_func=lambda **_: {"choices": [{"message": {"content": generated_code}}]}
        ),
    )

    response = service.chat(
        ChatRequest(
            message="Output a torus",
            tree_state=_seed_tree(),
            llm_model="test-model",
        )
    )

    assert [operation.tool for operation in response.operations_executed] == ["create_torus"]
    assert response.operations_executed[0].arguments == {
        "major_radius": 30.0,
        "minor_radius": 10.0,
    }


def test_validation_retry_teaches_boolean_overlap() -> None:
    invalid_code = (
        "from opencad import Part, Sketch\n"
        "left = Part(name='Left').box(2, 2, 2)\n"
        "profile = Sketch(name='Remote').rect(2, 2, origin=(10, 10))\n"
        "right = Part(name='Right').extrude(profile, depth=2)\n"
        "result = left.union(right)\n"
    )
    corrected_code = (
        "from opencad import Part, Sketch\n"
        "shank = Part(name='Shank').cylinder(3, 30)\n"
        "head = Part(name='Head').cylinder(7, 5)\n"
        "result = shank.union(head)\n"
    )
    user_messages: list[str] = []

    def completion(**kwargs: object) -> dict[str, object]:
        messages = kwargs["messages"]
        assert isinstance(messages, list)
        user_messages.append(str(messages[-1]["content"]))
        code = invalid_code if len(user_messages) == 1 else corrected_code
        return {"choices": [{"message": {"content": code}}]}

    service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(completion_func=completion),
    )

    response = service.chat(
        ChatRequest(message="Build a screw", tree_state=_seed_tree(), llm_model="test")
    )

    assert len(user_messages) == 2
    assert "bounding boxes overlap" in user_messages[1]
    assert "narrow cylinder for the shank" in user_messages[1]
    assert [operation.tool for operation in response.operations_executed] == [
        "create_cylinder",
        "create_cylinder",
        "boolean_union",
    ]


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
                llm_model="test-model",
            )
        )


def test_healthz() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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


def test_live_kernel_fillet_resolves_topology_from_shape_owner() -> None:
    generated_code = (
        "from opencad import Part, Sketch\n"
        "base = Part(name='Base').box(10, 10, 4)\n"
        "hole = Part(name='Hole').cylinder(2, 4)\n"
        "result = base.cut(hole).fillet(edges='all', radius=0.5)\n"
    )
    kernel = OpenCadKernel(id_strategy="uuid")
    registry = OperationRegistry(kernel)

    def kernel_call(operation: str, payload: dict[str, object]) -> dict[str, object]:
        return registry.call(operation, payload).model_dump()

    service = OpenCadAgentService(
        kernel_call=kernel_call,
        kernel_topology_call=lambda shape_id: kernel.get_topology(shape_id).model_dump(),
        live_kernel=True,
        llm_client=LiteLlmProvider(
            completion_func=lambda **_: {
                "choices": [{"message": {"content": generated_code}}]
            }
        ),
    )

    response = service.chat(
        ChatRequest(
            message="Build and fillet a drilled block",
            tree_state=_seed_tree(),
            llm_model="test-model",
        )
    )

    assert [operation.tool for operation in response.operations_executed] == [
        "create_box",
        "create_cylinder",
        "boolean_cut",
        "fillet_edges",
    ]


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
            llm_provider="openai",
            llm_model="gpt-5.5",
        )
    )

    assert response.operations_executed == []
    assert response.generated_code == expected_code
    assert captured["model"] == "openai/gpt-5.5"
    assert "temperature" not in captured
    assert "reasoning_effort" not in captured
    messages = captured["messages"]
    assert isinstance(messages, list)
    system_messages = [message for message in messages if message["role"] == "system"]
    assert system_messages
    assert any("Valid repeated-feature composition example" in message["content"] for message in system_messages)



def test_service_uses_environment_litellm_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCAD_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENCAD_LLM_MODEL", "gpt-5.5")
    captured: dict[str, object] = {}
    expected_code = """from opencad import Part, Sketch

Part(name="Env LLM Part")"""

    def fake_completion(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"choices": [{"message": {"content": expected_code}}]}

    service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(completion_func=fake_completion),
    )
    response = service.chat(
        ChatRequest(
            message="Generate a motor script",
            tree_state=_seed_tree(),
            conversation_history=[],
        )
    )

    assert response.generated_code == expected_code
    assert captured["model"] == "openai/gpt-5.5"
    assert "temperature" not in captured


def test_ollama_always_uses_fixed_non_reasoning_mode() -> None:
    captured: dict[str, object] = {}
    provider = LiteLlmProvider(
        completion_func=lambda **kwargs: (
            captured.update(kwargs) or {"choices": [{"message": {"content": "Part(name='Test')"}}]}
        )
    )

    provider.generate_code(
        provider="ollama",
        model="qwen2.5-coder:7b",
        system_prompt="Generate code",
        user_message="Build a part",
        conversation_history=[],
    )

    assert captured["model"] == "ollama/qwen2.5-coder:7b"
    assert captured["temperature"] == 0.2
    assert captured["reasoning_effort"] == "none"


def test_chat_requires_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCAD_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENCAD_LLM_MODEL", raising=False)
    service = OpenCadAgentService(live_kernel=False)

    with pytest.raises(AgentConfigurationError, match="requires an LLM"):
        service.chat(
            ChatRequest(
                message="Build a cog",
                tree_state=_seed_tree(),
            )
        )


def test_chat_reports_missing_litellm_as_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCAD_LLM_MODEL", "test-model")

    def missing_litellm(**_: object) -> object:
        raise ModuleNotFoundError("No module named 'litellm'", name="litellm")

    service = OpenCadAgentService(
        live_kernel=False,
        llm_client=LiteLlmProvider(completion_func=missing_litellm),
    )

    with pytest.raises(AgentConfigurationError, match="uv sync --extra llm"):
        service.chat(ChatRequest(message="Build a cog", tree_state=_seed_tree()))


def test_chat_request_requires_model_when_provider_is_set() -> None:
    with pytest.raises(ValueError, match="llm_model is required"):
        ChatRequest(
            message="Generate a mounting bracket script",
            tree_state=_seed_tree(),
            conversation_history=[],
            llm_provider="openai",
        )


@pytest.mark.parametrize("removed_field", ["reasoning", "generate_code"])
def test_chat_request_rejects_removed_execution_modes(removed_field: str) -> None:
    with pytest.raises(ValueError, match=removed_field):
        ChatRequest.model_validate({
            "message": "Build a cog",
            "tree_state": _seed_tree().model_dump(),
            removed_field: True,
        })
