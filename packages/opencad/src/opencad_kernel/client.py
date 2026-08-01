"""Transport-agnostic kernel access contract.

Core packages depend on :class:`KernelClient` only. The in-process
implementation lives here; the HTTP implementation lives in the backend
web layer so that no core module carries a network dependency.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from opencad_kernel.core.models import Success
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.registry import OperationRegistry


@runtime_checkable
class KernelClient(Protocol):
    """The kernel surface that feature-tree, agent, and runtime code needs."""

    def call_operation(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a kernel operation and return an HTTP-shaped response dict.

        Success responses carry ``ok=True``, ``shape_id``, and ``metadata``;
        failures carry ``ok=False``, ``code``, ``message``, and ``suggestion``.
        """
        ...

    def get_topology(self, shape_id: str) -> dict[str, Any]:
        """Return the shape's topology map as a plain dict."""
        ...

    def get_mesh(self, shape_id: str, deflection: float = 0.1) -> dict[str, Any]:
        """Return tessellated mesh data for the shape as a plain dict."""
        ...


def result_to_dict(result: Any) -> dict[str, Any]:
    """Convert an ``OperationResult`` into the wire-compatible response dict."""
    if isinstance(result, Success):
        return {
            "ok": True,
            "shape_id": result.shape_id,
            "metadata": result.metadata,
        }
    return {
        "ok": False,
        "code": result.code,
        "message": result.message,
        "suggestion": result.suggestion,
    }


class LocalKernelClient:
    """In-process :class:`KernelClient` backed by an ``OperationRegistry``."""

    def __init__(self, registry: OperationRegistry, kernel: OpenCadKernel | None = None) -> None:
        self.registry = registry
        self.kernel = kernel if kernel is not None else registry.kernel

    def call_operation(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        return result_to_dict(self.registry.call(operation, params))

    def get_topology(self, shape_id: str) -> dict[str, Any]:
        return self.kernel.get_topology(shape_id).model_dump()

    def get_mesh(self, shape_id: str, deflection: float = 0.1) -> dict[str, Any]:
        return self.kernel.tessellate(shape_id, deflection).model_dump()


__all__ = ["KernelClient", "LocalKernelClient", "result_to_dict"]
