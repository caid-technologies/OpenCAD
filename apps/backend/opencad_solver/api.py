from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()
from typing import Any

from fastapi import FastAPI, APIRouter

from opencad.api_app import create_api_app
from opencad.version import __version__
from opencad_solver.backend import SolverBackend
from opencad_solver.models import CheckResult, ConstraintDiagnostics, Sketch, SolveResult
from opencad_solver.solver import PythonSolverBackend
from opencad_solver.solvespace_backend import SolveSpaceBackend, is_available as slvs_available

app: FastAPI = create_api_app(title="OpenCAD Solver", version=__version__)
router = APIRouter()

# ── Backend selection ───────────────────────────────────────────────

def _make_backend() -> SolverBackend:
    """Select solver backend from ``OPENCAD_SOLVER_BACKEND`` env var.

    Supported values:
    - ``solvespace`` — use SolveSpace (requires ``python-solvespace``).
    - ``python`` (default) — built-in NumPy/SciPy Gauss-Newton solver.
    - ``auto`` — SolveSpace if available, else Python fallback.
    """
    choice = os.environ.get("OPENCAD_SOLVER_BACKEND", "auto").lower()
    if choice == "solvespace":
        return SolveSpaceBackend()
    if choice == "python":
        return PythonSolverBackend()
    # auto: prefer SolveSpace when importable
    if slvs_available():
        return SolveSpaceBackend()
    return PythonSolverBackend()


_backend: SolverBackend = _make_backend()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/backend")
def backend_info() -> dict[str, Any]:
    """Report which solver backend is active and its capabilities."""
    return {
        "name": _backend.name,
        "supports_3d": _backend.supports_3d,
        "solvespace_available": slvs_available(),
    }


@router.post("/sketch/solve", response_model=SolveResult)
def solve_endpoint(sketch: Sketch) -> SolveResult:
    return _backend.solve(sketch)


@router.post("/sketch/check", response_model=CheckResult)
def check_endpoint(sketch: Sketch) -> CheckResult:
    return _backend.check(sketch)


@router.post("/sketch/diagnose", response_model=ConstraintDiagnostics)
def diagnose_endpoint(sketch: Sketch) -> ConstraintDiagnostics:
    """Full constraint-graph introspection.

    Returns DOF count, over/under-constrained status, Jacobian sparse
    structure, and variable ↔ constraint index mapping.
    """
    return _backend.diagnose(sketch)


app.include_router(router)
