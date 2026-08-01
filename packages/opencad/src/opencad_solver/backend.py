"""Solver backend protocol — the swap boundary for constraint solvers.

Any class implementing this protocol can serve as the constraint-solving
engine behind the OpenCAD solver service.  Today: built-in Python/NumPy
Gauss-Newton solver.  Optionally: SolveSpace via python-solvespace bindings.

**v1 scope:** 2-D sketch constraints with pluggable backend selection and
full constraint-graph introspection (DOF, Jacobian structure, variable/
constraint mapping).  3-D assembly mate evaluation is routed through the
kernel's mate store and calls ``diagnose`` on the active backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from opencad_solver.models import (
    CheckResult,
    ConstraintDiagnostics,
    Sketch,
    SolveResult,
)


class SolverBackend(ABC):
    """Abstract constraint-solver backend.

    Implementations must provide ``solve``, ``check``, and ``diagnose``.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend identifier (e.g. ``'python'``, ``'solvespace'``)."""
        ...

    @property
    def supports_3d(self) -> bool:
        """Whether this backend can evaluate 3-D assembly constraints."""
        return False

    @abstractmethod
    def solve(
        self,
        sketch: Sketch,
        *,
        max_iterations: int = 200,
        tolerance: float = 1e-6,
    ) -> SolveResult:
        """Solve the constraint system and return updated geometry."""
        ...

    @abstractmethod
    def check(
        self,
        sketch: Sketch,
        *,
        tolerance: float = 1e-6,
    ) -> CheckResult:
        """Evaluate constraint satisfaction without modifying geometry."""
        ...

    @abstractmethod
    def diagnose(
        self,
        sketch: Sketch,
        *,
        tolerance: float = 1e-6,
    ) -> ConstraintDiagnostics:
        """Return full constraint-graph introspection diagnostics."""
        ...
