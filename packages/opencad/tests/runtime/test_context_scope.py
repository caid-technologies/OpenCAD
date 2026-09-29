import asyncio
from contextvars import Context

import pytest

from opencad import (
    Part,
    RuntimeContext,
    get_default_context,
    reset_default_context,
    set_default_context,
    use_default_context,
)


@pytest.fixture(autouse=True)
def analytic_backend(monkeypatch):
    monkeypatch.setenv("OPENCAD_KERNEL_BACKEND", "analytic")


def test_fresh_execution_contexts_get_distinct_lazy_runtimes():
    first, second = Context(), Context()
    first_runtime = first.run(get_default_context)
    second_runtime = second.run(get_default_context)
    assert first_runtime is not second_runtime
    assert first.run(get_default_context) is first_runtime
    replacement = first.run(reset_default_context)
    assert replacement is not first_runtime
    assert first.run(get_default_context) is replacement
    assert second.run(get_default_context) is second_runtime


@pytest.mark.parametrize("fail", [False, True])
def test_scope_restores_previous_binding_after_reset_and_nested_execution(fail):
    caller, outer, inner = RuntimeContext(), RuntimeContext(), RuntimeContext()
    with use_default_context(caller):
        try:
            with use_default_context(outer) as bound:
                assert bound is outer
                assert Part().context is outer
                with use_default_context(inner):
                    assert Part().context is inner
                    reset_default_context()
                    assert get_default_context() is not inner
                assert get_default_context() is outer
                set_default_context(RuntimeContext())
                if fail:
                    raise ValueError("scope failed")
        except ValueError as exc:
            assert str(exc) == "scope failed"
        assert get_default_context() is caller


def test_scope_restores_unbound_context():
    execution = Context()
    temporary = RuntimeContext()

    def scoped_work():
        with use_default_context(temporary):
            assert get_default_context() is temporary

    execution.run(scoped_work)
    assert execution.run(get_default_context) is not temporary


def test_overlapping_async_scopes_restore_the_inherited_caller():
    caller = RuntimeContext()

    async def exercise():
        started = [asyncio.Event(), asyncio.Event()]

        async def worker(index):
            runtime = RuntimeContext()
            with use_default_context(runtime):
                started[index].set()
                await asyncio.wait_for(started[1 - index].wait(), timeout=5)
                part = Part().box(1, 1, 1, name=f"task-{index}")
                assert part.context is runtime
            assert get_default_context() is caller
            return runtime

        first, second = await asyncio.gather(worker(0), worker(1))
        assert first is not second
        for index, runtime in enumerate([first, second]):
            assert [n.name for n in runtime.tree.nodes.values()] == [
                "Root",
                f"task-{index}",
            ]
        assert get_default_context() is caller

    with use_default_context(caller):
        asyncio.run(exercise())
