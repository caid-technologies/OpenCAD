from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

import pytest

from opencad import (
    Part,
    RuntimeContext,
    Sketch,
    get_default_context,
    reset_default_context,
    set_default_context,
)
from opencad_agent import run_chat
from opencad_agent.generated_code import execute_generated_code
from opencad_agent.llm import LiteLlmProvider
from opencad_agent.models import ChatRequest
from opencad_agent.service import (
    GeneratedCodeExecutionError,
    GeneratedCodeValidationError,
    OpenCadAgentService,
)


@pytest.fixture(autouse=True)
def isolated_caller(monkeypatch):
    monkeypatch.setenv("OPENCAD_KERNEL_BACKEND", "analytic")
    previous = get_default_context()
    caller = reset_default_context()
    yield caller
    set_default_context(previous)


def service_for(code, **kwargs):
    completion = Mock(return_value={"choices": [{"message": {"content": code}}]})
    return OpenCadAgentService(
        llm_client=LiteLlmProvider(completion_func=completion), **kwargs
    ), completion


def feature_names(tree):
    return [node.name for node in tree.nodes.values() if node.id != tree.root_id]


def test_run_chat_preserves_caller_and_keeps_validation_geometry_separate(
    isolated_caller, monkeypatch
):
    monkeypatch.setenv("OPENCAD_LLM_MODEL", "offline-test")
    caller = isolated_caller
    Part().box(1, 1, 1, name="before")
    service, completion = service_for(
        'from opencad import Part\nPart().box(2, 2, 2, name="agent")',
        kernel_client=caller.kernel_client,
        live_kernel=True,
    )

    _, operations = run_chat(caller, "Create a box", service=service)

    assert get_default_context() is caller
    assert feature_names(caller.tree) == ["before", "agent"]
    assert len(caller.kernel.store.all_ids()) == 2  # No validation shapes leaked.
    assert len(operations) == 1
    completion.assert_called_once()
    after = Part().box(3, 3, 3, name="after")
    sketch = Sketch().rect(2, 2)
    assert after.context is caller
    assert sketch._context is caller
    assert feature_names(caller.tree)[:3] == ["before", "agent", "after"]


@pytest.mark.parametrize("phase", ["validation", "execution"])
def test_failed_agent_execution_restores_caller(isolated_caller, phase):
    caller = isolated_caller
    before = caller.tree.model_dump()
    service = OpenCadAgentService(live_kernel=False)
    code = "from opencad import Part\nPart().box(1, 1, 1)\n1 / 0"

    method = (
        service._validate_generated_code
        if phase == "validation"
        else service._run_generated_code
    )
    error = (
        GeneratedCodeValidationError
        if phase == "validation"
        else GeneratedCodeExecutionError
    )
    with pytest.raises(error, match="division by zero"):
        method(code, caller.tree)

    assert get_default_context() is caller
    assert caller.tree.model_dump() == before
    assert caller.kernel.store.all_ids() == []


def test_nested_agent_execution_restores_outer_scope(isolated_caller, monkeypatch):
    caller = isolated_caller
    outer, inner = RuntimeContext(), RuntimeContext()
    service = OpenCadAgentService(live_kernel=False)

    def nested_execute(code):
        if code == "outer":
            assert get_default_context() is outer
            Part().box(1, 1, 1, name="outer-before")
            service._execute_code_in_context("inner", inner)
            assert get_default_context() is outer
            Part().box(1, 1, 1, name="outer-after")
        else:
            assert get_default_context() is inner
            Part().box(1, 1, 1, name="inner")

    monkeypatch.setattr("opencad_agent.service.execute_generated_code", nested_execute)
    service._execute_code_in_context("outer", outer)

    assert get_default_context() is caller
    assert feature_names(outer.tree) == ["outer-before", "outer-after"]
    assert feature_names(inner.tree) == ["inner"]


def test_concurrent_chats_on_one_service_keep_trees_and_operations_separate(
    isolated_caller, monkeypatch
):
    # Every chat validates and then executes. At each stage, both contexts must
    # be bound before either script runs, and both scripts finish before cleanup.
    # This deterministically exposes a process-global binding without sleeps.
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
    service = OpenCadAgentService(
        live_kernel=False, llm_client=LiteLlmProvider(completion_func=provider)
    )

    def chat(name):
        worker_caller = reset_default_context()
        response = service.chat(
            ChatRequest(
                message=name, tree_state=worker_caller.tree, llm_model="offline-test"
            )
        )
        assert get_default_context() is worker_caller
        assert feature_names(worker_caller.tree) == []
        return response

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(chat, "request-A")
        second = pool.submit(chat, "request-B")
        responses = [first.result(timeout=30), second.result(timeout=30)]

    assert provider.call_count == 2
    for name, response in zip(["request-A", "request-B"], responses):
        assert feature_names(response.new_tree_state) == [name]
        assert len(response.operations_executed) == 1
        assert response.operations_executed[0].result["shape_id"] == next(
            node.shape_id
            for node in response.new_tree_state.nodes.values()
            if node.name == name
        )
    assert get_default_context() is isolated_caller
