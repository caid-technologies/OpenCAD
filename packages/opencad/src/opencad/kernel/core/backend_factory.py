"""Centralized geometry-backend selection.

The analytic backend is useful for validation and lightweight tests, but it
does not own native B-rep geometry.  Callers that produce exchange files must
therefore request a native backend instead of silently accepting the analytic
fallback.
"""

from __future__ import annotations

from typing import Literal

from opencad.kernel.core.analytic_backend import AnalyticBackend
from opencad.kernel.core.backend import KernelBackend
from opencad.kernel.core.store import IdStrategy

BackendName = Literal["analytic", "auto", "occt"]


class BackendUnavailableError(RuntimeError):
    """Raised when the requested geometry backend cannot be constructed."""


def create_backend(
    name: BackendName | str = "auto",
    *,
    id_strategy: IdStrategy = "uuid",
    require_native: bool = False,
) -> KernelBackend:
    """Create a geometry backend for an application entry point.

    ``auto`` prefers OCCT and falls back to the analytic backend only when
    native geometry is not required.  ``require_native`` is intended for STEP
    and other exchange-file workflows where analytic metadata is insufficient.
    """
    if name not in {"analytic", "auto", "occt"}:
        raise ValueError(f"Unknown geometry backend: {name}")

    if name == "analytic":
        if require_native:
            raise BackendUnavailableError(
                "The analytic backend cannot export a real STEP file. "
                "Use --backend occt and install it with: uv sync --extra occt"
            )
        return AnalyticBackend(id_strategy=id_strategy)

    try:
        from opencad.kernel.core.occt_backend import HAS_OCCT, OcctBackend
    except ImportError as exc:
        if name == "occt" or require_native:
            raise BackendUnavailableError(
                "The OCCT backend is required but CadQuery/OCP is not installed. "
                "Install it with: uv sync --extra occt"
            ) from exc
    else:
        if HAS_OCCT:
            return OcctBackend(id_strategy=id_strategy)

    if name == "occt" or require_native:
        raise BackendUnavailableError(
            "The OCCT backend is required but CadQuery/OCP is not installed. "
            "Install it with: uv sync --extra occt"
        )

    return AnalyticBackend(id_strategy=id_strategy)
