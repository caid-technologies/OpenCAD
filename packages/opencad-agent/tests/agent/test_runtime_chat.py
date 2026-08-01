from __future__ import annotations

from opencad import reset_default_context

from opencad_agent import run_chat


def test_runtime_chat_executes_in_process() -> None:
    ctx = reset_default_context()
    response, operations = run_chat(
        ctx,
        "Create a mounting bracket with 4 standoffs, a central cutout, and counterbored mounting ears"
    )

    assert "bracket" in response.lower()
    assert len(operations) >= 8
    assert any(node.operation == "boolean_cut" for node in ctx.tree.nodes.values())
