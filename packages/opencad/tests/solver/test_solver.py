from __future__ import annotations

import math

import pytest

from opencad.solver.models import (
    Constraint,
    ConstraintDiagnostics,
    ConstraintType,
    LineEntity,
    PointEntity,
    Sketch,
    SolveStatus,
)
from opencad.solver.solver import (
    PythonSolverBackend,
    check_sketch,
    diagnose_sketch,
    solve_sketch,
)
from opencad.solver.solvespace_backend import SolveSpaceBackend, SolveSpaceUnavailableError, is_available


def test_simple_rectangle_solves() -> None:
    sketch = Sketch(
        entities={
            "p1": PointEntity(id="p1", x=0.0, y=0.0),
            "p2": PointEntity(id="p2", x=4.2, y=0.3),
            "p3": PointEntity(id="p3", x=4.0, y=1.8),
            "p4": PointEntity(id="p4", x=-0.3, y=2.2),
        },
        constraints=[
            Constraint(id="c1", type=ConstraintType.FIXED, a="p1"),
            Constraint(id="c2", type=ConstraintType.HORIZONTAL, a="p1", b="p2"),
            Constraint(id="c3", type=ConstraintType.VERTICAL, a="p2", b="p3"),
            Constraint(id="c4", type=ConstraintType.HORIZONTAL, a="p3", b="p4"),
            Constraint(id="c5", type=ConstraintType.VERTICAL, a="p4", b="p1"),
            Constraint(id="c6", type=ConstraintType.DISTANCE, a="p1", b="p2", value=4.0),
            Constraint(id="c7", type=ConstraintType.DISTANCE, a="p2", b="p3", value=2.0),
        ],
    )

    result = solve_sketch(sketch)
    assert result.status == SolveStatus.SOLVED

    solved = result.sketch.entities
    p1 = solved["p1"]
    p2 = solved["p2"]
    p3 = solved["p3"]
    assert isinstance(p1, PointEntity)
    assert isinstance(p2, PointEntity)
    assert isinstance(p3, PointEntity)
    assert math.hypot(p2.x - p1.x, p2.y - p1.y) == pytest.approx(4.0, abs=1e-4)
    assert math.hypot(p3.x - p2.x, p3.y - p2.y) == pytest.approx(2.0, abs=1e-4)


def test_parallel_lines_case_is_underconstrained() -> None:
    sketch = Sketch(
        entities={
            "l1": LineEntity(id="l1", x1=0.0, y1=0.0, x2=2.0, y2=0.0),
            "l2": LineEntity(id="l2", x1=0.0, y1=1.0, x2=1.5, y2=2.0),
        },
        constraints=[
            Constraint(id="c1", type=ConstraintType.FIXED, a="l1"),
            Constraint(id="c2", type=ConstraintType.PARALLEL, a="l1", b="l2"),
        ],
    )

    result = solve_sketch(sketch)
    assert result.status == SolveStatus.UNDERCONSTRAINED


def test_tangent_circle_line_case() -> None:
    sketch = Sketch(
        entities={
            "line": LineEntity(id="line", x1=-5.0, y1=0.0, x2=5.0, y2=0.0),
            "c": {
                "id": "c",
                "type": "circle",
                "cx": 0.4,
                "cy": 2.5,
                "radius": 1.0,
            },
        },
        constraints=[
            Constraint(id="c1", type=ConstraintType.FIXED, a="line"),
            Constraint(id="c2", type=ConstraintType.TANGENT, a="c", b="line"),
        ],
    )

    result = solve_sketch(sketch)
    assert result.status in {SolveStatus.SOLVED, SolveStatus.UNDERCONSTRAINED}
    assert result.max_residual < 1e-3


def test_overconstrained_case_returns_conflict() -> None:
    sketch = Sketch(
        entities={
            "p1": PointEntity(id="p1", x=0.0, y=0.0),
            "p2": PointEntity(id="p2", x=1.0, y=0.0),
        },
        constraints=[
            Constraint(id="fixed_a", type=ConstraintType.FIXED, a="p1"),
            Constraint(id="fixed_b", type=ConstraintType.FIXED, a="p2"),
            Constraint(id="dist", type=ConstraintType.DISTANCE, a="p1", b="p2", value=3.0),
        ],
    )

    result = solve_sketch(sketch)
    assert result.status == SolveStatus.OVERCONSTRAINED
    assert result.conflict_constraint_id is not None


def test_underconstrained_case() -> None:
    sketch = Sketch(
        entities={
            "p1": PointEntity(id="p1", x=0.0, y=0.0),
            "p2": PointEntity(id="p2", x=2.0, y=1.0),
        },
        constraints=[
            Constraint(id="dist", type=ConstraintType.DISTANCE, a="p1", b="p2", value=2.5),
        ],
    )

    result = solve_sketch(sketch)
    assert result.status == SolveStatus.UNDERCONSTRAINED


def test_check_endpoint_flags_underconstrained() -> None:
    sketch = Sketch(
        entities={
            "p1": PointEntity(id="p1", x=0.0, y=0.0),
            "p2": PointEntity(id="p2", x=1.0, y=0.0),
        },
        constraints=[Constraint(id="dist", type=ConstraintType.DISTANCE, a="p1", b="p2", value=1.0)],
    )

    result = check_sketch(sketch)
    assert result.status == SolveStatus.UNDERCONSTRAINED


def test_missing_constraint_reference_reports_conflict() -> None:
    sketch = Sketch(
        entities={"p1": PointEntity(id="p1", x=0.0, y=0.0)},
        constraints=[Constraint(id="bad", type=ConstraintType.DISTANCE, a="p1", b="missing", value=2.0)],
    )

    result = solve_sketch(sketch)
    assert result.status == SolveStatus.OVERCONSTRAINED
    assert result.conflict_constraint_id == "bad"
    assert "missing entity" in result.message


# ── Constraint-graph introspection ──────────────────────────────────


class TestDiagnoseSketch:
    def test_diagnose_fully_constrained(self) -> None:
        sketch = Sketch(
            entities={
                "p1": PointEntity(id="p1", x=0.0, y=0.0),
                "p2": PointEntity(id="p2", x=4.2, y=0.3),
            },
            constraints=[
                Constraint(id="f1", type=ConstraintType.FIXED, a="p1"),
                Constraint(id="f2", type=ConstraintType.FIXED, a="p2"),
            ],
        )
        diag = diagnose_sketch(sketch)
        assert isinstance(diag, ConstraintDiagnostics)
        assert diag.dof == 0
        assert diag.status == SolveStatus.SOLVED
        assert diag.jacobian.rows > 0
        assert diag.jacobian.cols > 0
        assert diag.jacobian.rank > 0
        assert len(diag.variables) == 4  # 2 points × 2 params
        assert len(diag.constraints) == 2

    def test_diagnose_underconstrained(self) -> None:
        sketch = Sketch(
            entities={
                "p1": PointEntity(id="p1", x=0.0, y=0.0),
                "p2": PointEntity(id="p2", x=2.0, y=1.0),
            },
            constraints=[
                Constraint(id="dist", type=ConstraintType.DISTANCE, a="p1", b="p2", value=2.5),
            ],
        )
        diag = diagnose_sketch(sketch)
        assert diag.dof > 0
        assert diag.status == SolveStatus.UNDERCONSTRAINED

    def test_diagnose_overconstrained(self) -> None:
        sketch = Sketch(
            entities={
                "p1": PointEntity(id="p1", x=0.0, y=0.0),
                "p2": PointEntity(id="p2", x=1.0, y=0.0),
            },
            constraints=[
                Constraint(id="fixed_a", type=ConstraintType.FIXED, a="p1"),
                Constraint(id="fixed_b", type=ConstraintType.FIXED, a="p2"),
                Constraint(id="dist", type=ConstraintType.DISTANCE, a="p1", b="p2", value=3.0),
            ],
        )
        diag = diagnose_sketch(sketch)
        assert diag.status == SolveStatus.OVERCONSTRAINED
        assert len(diag.over_constrained_ids) > 0

    def test_diagnose_empty_constraints(self) -> None:
        sketch = Sketch(
            entities={"p1": PointEntity(id="p1", x=0.0, y=0.0)},
            constraints=[],
        )
        diag = diagnose_sketch(sketch)
        assert diag.dof == 2  # free point in 2D
        assert diag.status == SolveStatus.UNDERCONSTRAINED
        assert diag.jacobian.rows == 0

    def test_diagnose_missing_reference(self) -> None:
        sketch = Sketch(
            entities={"p1": PointEntity(id="p1", x=0.0, y=0.0)},
            constraints=[Constraint(id="bad", type=ConstraintType.DISTANCE, a="p1", b="nope", value=1.0)],
        )
        diag = diagnose_sketch(sketch)
        assert diag.status == SolveStatus.OVERCONSTRAINED
        assert "bad" in diag.over_constrained_ids

    def test_diagnose_jacobian_sparsity(self) -> None:
        sketch = Sketch(
            entities={
                "p1": PointEntity(id="p1", x=0.0, y=0.0),
                "p2": PointEntity(id="p2", x=3.0, y=0.0),
            },
            constraints=[
                Constraint(id="f1", type=ConstraintType.FIXED, a="p1"),
                Constraint(id="dist", type=ConstraintType.DISTANCE, a="p1", b="p2", value=3.0),
            ],
        )
        diag = diagnose_sketch(sketch)
        assert len(diag.jacobian.nonzero_entries) > 0
        for row, col in diag.jacobian.nonzero_entries:
            assert 0 <= row < diag.jacobian.rows
            assert 0 <= col < diag.jacobian.cols

    def test_diagnose_variable_mapping(self) -> None:
        sketch = Sketch(
            entities={
                "p1": PointEntity(id="p1", x=1.0, y=2.0),
                "l1": LineEntity(id="l1", x1=0.0, y1=0.0, x2=5.0, y2=0.0),
            },
            constraints=[Constraint(id="h", type=ConstraintType.HORIZONTAL, a="l1")],
        )
        diag = diagnose_sketch(sketch)
        entity_ids = {v.entity_id for v in diag.variables}
        assert "p1" in entity_ids
        assert "l1" in entity_ids
        param_names = {v.parameter_name for v in diag.variables}
        assert "x" in param_names
        assert "x1" in param_names


# ── Diagnose API endpoint ──────────────────────────────────────────


# ── Backend info endpoint ──────────────────────────────────────────


# ── PythonSolverBackend ────────────────────────────────────────────


class TestPythonSolverBackend:
    def test_solve_attaches_diagnostics(self) -> None:
        backend = PythonSolverBackend()
        sketch = Sketch(
            entities={
                "p1": PointEntity(id="p1", x=0.0, y=0.0),
                "p2": PointEntity(id="p2", x=1.0, y=0.0),
            },
            constraints=[
                Constraint(id="f1", type=ConstraintType.FIXED, a="p1"),
                Constraint(id="f2", type=ConstraintType.FIXED, a="p2"),
            ],
        )
        result = backend.solve(sketch)
        assert result.diagnostics is not None
        assert result.diagnostics.dof == 0

    def test_check_attaches_diagnostics(self) -> None:
        backend = PythonSolverBackend()
        sketch = Sketch(
            entities={"p1": PointEntity(id="p1", x=0.0, y=0.0)},
            constraints=[Constraint(id="f1", type=ConstraintType.FIXED, a="p1")],
        )
        result = backend.check(sketch)
        assert result.diagnostics is not None

    def test_backend_name(self) -> None:
        assert PythonSolverBackend().name == "python"

    def test_backend_no_3d(self) -> None:
        assert PythonSolverBackend().supports_3d is False


# ── SolveSpaceBackend ──────────────────────────────────────────────


class TestSolveSpaceBackend:
    def test_unavailable_raises(self) -> None:
        if is_available():
            pytest.skip("SolveSpace is installed — cannot test unavailable path")
        backend = SolveSpaceBackend()
        sketch = Sketch(
            entities={"p1": PointEntity(id="p1", x=0.0, y=0.0)},
            constraints=[],
        )
        with pytest.raises(SolveSpaceUnavailableError):
            backend.solve(sketch)
        with pytest.raises(SolveSpaceUnavailableError):
            backend.check(sketch)
        with pytest.raises(SolveSpaceUnavailableError):
            backend.diagnose(sketch)

    def test_is_available_returns_bool(self) -> None:
        assert isinstance(is_available(), bool)

    def test_backend_name(self) -> None:
        assert SolveSpaceBackend().name == "solvespace"


# ── Solve/check results include optional diagnostics field ─────────


def test_solve_result_has_diagnostics_field() -> None:
    """Backwards compatibility: diagnostics is optional and defaults None."""
    sketch = Sketch(
        entities={"p1": PointEntity(id="p1", x=0.0, y=0.0)},
        constraints=[Constraint(id="f", type=ConstraintType.FIXED, a="p1")],
    )
    result = solve_sketch(sketch)
    # Module-level solve_sketch does NOT attach diagnostics (backend does)
    assert result.diagnostics is None


def test_check_result_has_diagnostics_field() -> None:
    sketch = Sketch(
        entities={"p1": PointEntity(id="p1", x=0.0, y=0.0)},
        constraints=[Constraint(id="f", type=ConstraintType.FIXED, a="p1")],
    )
    result = check_sketch(sketch)
    assert result.diagnostics is None
