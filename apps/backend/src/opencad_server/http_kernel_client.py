"""HTTP-backed :class:`~opencad.kernel.client.KernelClient`.

This is the only place in the codebase that speaks HTTP *to* the kernel.
Core packages take a ``KernelClient`` and stay transport-agnostic.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_KERNEL_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 30.0


def kernel_base_url() -> str:
    """Resolve the kernel base URL, normalising the ``/kernel`` mount prefix."""
    base_url = os.environ.get("OPENCAD_KERNEL_URL", DEFAULT_KERNEL_URL).rstrip("/")
    if not base_url.endswith("/kernel"):
        base_url = f"{base_url}/kernel"
    return base_url


class HttpKernelClient:
    """Call a remote OpenCAD kernel service over HTTP."""

    def __init__(self, base_url: str | None = None, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = (base_url or kernel_base_url()).rstrip("/")
        self.timeout = timeout

    def call_operation(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/operations/{operation}",
            json={"payload": params},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_topology(self, shape_id: str) -> dict[str, Any]:
        response = httpx.get(f"{self.base_url}/shapes/{shape_id}/topology", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_mesh(self, shape_id: str, deflection: float = 0.1) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}/shapes/{shape_id}/mesh",
            params={"deflection": deflection},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()


__all__ = ["HttpKernelClient", "kernel_base_url", "DEFAULT_KERNEL_URL"]
