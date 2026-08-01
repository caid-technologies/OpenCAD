"""Drive an OpenCAD ``RuntimeContext`` with the LLM agent.

This lives in ``opencad_agent`` rather than ``opencad`` so the core stays
free of any agent or LLM dependency: the arrow points core ← agent, never
the other way around.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opencad_agent.models import ChatRequest
from opencad_agent.service import OpenCadAgentService

if TYPE_CHECKING:
    from opencad.runtime import RuntimeContext


def run_chat(
    context: RuntimeContext,
    message: str,
    *,
    service: OpenCadAgentService | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Run the agent in-process against ``context`` and merge the result.

    The context's kernel executes the geometry, so generated features land in
    the same shape store the fluent API uses. Returns the assistant response
    and the executed operations.
    """
    service = service or OpenCadAgentService(kernel_client=context.kernel_client, live_kernel=True)
    response = service.chat(
        ChatRequest(
            message=message,
            tree_state=context.tree,
            conversation_history=[],
        )
    )
    context.adopt_tree(response.new_tree_state)
    return response.response, [operation.model_dump() for operation in response.operations_executed]


__all__ = ["run_chat"]
