from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from opencad_solver.models import (
    ArcEntity,
    CheckResult,
    CircleEntity,
    Constraint,
    ConstraintDiagnostics,
    ConstraintInfo,
    ConstraintType,
    Entity,
    JacobianInfo,
    LineEntity,
    PointEntity,
    RectangleEntity,
    Sketch,
    SolveResult,
    SolveStatus,
    VariableInfo,
)

try:  # pragma: no cover - optional dependency
    from scipy.optimize import minimize as scipy_minimize
except Exception:  # pragma: no cover - optional dependency
    scipy_minimize = None


@dataclass
class _OptimizeResult:
    x: np.ndarray
    nit: int
    success: bool
    message: str


class _VectorCodec:
    def __init__(self, entities: dict[str, Entity]) -> None:
        self.order = list(entities.keys())
        self.slices: dict[str, tuple[int, int]] = {}
        cursor = 0
        for entity_id in self.order:
            size = self._size_of(entities[entity_id])
            self.slices[entity_id] = (cursor, cursor + size)
            cursor += size
        self.dimension = cursor

    def _size_of(self, entity: Entity) -> int:
        if isinstance(entity, PointEntity):
            return 2
        if isinstance(entity, LineEntity):
            return 4
        if isinstance(entity, CircleEntity):
            return 3
        if isinstance(entity, ArcEntity):
            return 5
        if isinstance(entity, RectangleEntity):
            return 4
        raise TypeError(f"Unsupported entity type: {type(entity)}")

    def to_vector(self, entities: dict[str, Entity]) -> np.ndarray:
        values: list[float] = []
        for entity_id in self.order:
            values.extend(_entity_to_params(entities[entity_id]))
        return np.array(values, dtype=float)

    def from_vector(self, vector: np.ndarray, entities_template: dict[str, Entity]) -> dict[str, Entity]:
        out: dict[str, Entity] = {}
        for entity_id in self.order:
            start, end = self.slices[entity_id]
            out[entity_id] = _params_to_entity(entities_template[entity_id], vector[start:end])
        return out


def _entity_to_params(entity: Entity) -> list[float]:
    if isinstance(entity, PointEntity):
        return [entity.x, entity.y]
    if isinstance(entity, LineEntity):
        return [entity.x1, entity.y1, entity.x2, entity.y2]
    if isinstance(entity, CircleEntity):
        return [entity.cx, entity.cy, entity.radius]
    if isinstance(entity, ArcEntity):
        return [entity.cx, entity.cy, entity.radius, entity.start_angle, entity.end_angle]
    if isinstance(entity, RectangleEntity):
        return [entity.x, entity.y, entity.width, entity.height]
    raise TypeError(f"Unsupported entity type: {type(entity)}")


def _params_to_entity(template: Entity, params: np.ndarray) -> Entity:
    if isinstance(template, PointEntity):
        return PointEntity(id=template.id, x=float(params[0]), y=float(params[1]))
    if isinstance(template, LineEntity):
        return LineEntity(
            id=template.id,
            x1=float(params[0]),
            y1=float(params[1]),
            x2=float(params[2]),
            y2=float(params[3]),
        )
    if isinstance(template, CircleEntity):
        return CircleEntity(
            id=template.id,
            cx=float(params[0]),
            cy=float(params[1]),
            radius=max(1e-6, abs(float(params[2]))),
        )
    if isinstance(template, ArcEntity):
        return ArcEntity(
            id=template.id,
            cx=float(params[0]),
            cy=float(params[1]),
            radius=max(1e-6, abs(float(params[2]))),
            start_angle=float(params[3]),
            end_angle=float(params[4]),
        )
    if isinstance(template, RectangleEntity):
        return RectangleEntity(
            id=template.id,
            x=float(params[0]),
            y=float(params[1]),
            width=max(1e-6, abs(float(params[2]))),
            height=max(1e-6, abs(float(params[3]))),
        )
    raise TypeError(f"Unsupported entity type: {type(template)}")


def _line_direction(line: LineEntity) -> np.ndarray:
    return np.array([line.x2 - line.x1, line.y2 - line.y1], dtype=float)


def _cross2d(a: np.ndarray, b: np.ndarray) -> float:
    return float((a[0] * b[1]) - (a[1] * b[0]))


def _line_length(line: LineEntity) -> float:
    return float(np.linalg.norm(_line_direction(line)))


def _line_start(line: LineEntity) -> np.ndarray:
    return np.array([line.x1, line.y1], dtype=float)


def _anchor(entity: Entity) -> np.ndarray:
    if isinstance(entity, PointEntity):
        return np.array([entity.x, entity.y], dtype=float)
    if isinstance(entity, LineEntity):
        return _line_start(entity)
    if isinstance(entity, CircleEntity):
        return np.array([entity.cx, entity.cy], dtype=float)
    if isinstance(entity, ArcEntity):
        return np.array([entity.cx, entity.cy], dtype=float)
    if isinstance(entity, RectangleEntity):
        return np.array([entity.x, entity.y], dtype=float)
    raise TypeError(f"Unsupported entity type: {type(entity)}")


def _point_line_distance(point: np.ndarray, line: LineEntity) -> float:
    a = np.array([line.x1, line.y1], dtype=float)
    b = np.array([line.x2, line.y2], dtype=float)
    ab = b - a
    denom = float(np.linalg.norm(ab))
    if denom <= 1e-12:
        return float(np.linalg.norm(point - a))
    return abs(_cross2d(ab, point - a)) / denom


def _constraint_residual(
    entities: dict[str, Entity],
    initial_params: dict[str, np.ndarray],
    constraint: Constraint,
) -> np.ndarray:
    penalty = np.array([1e3], dtype=float)
    a = entities.get(constraint.a)
    b = entities.get(constraint.b) if constraint.b else None

    if a is None:
        return penalty

    ctype = constraint.type
    if ctype == ConstraintType.HORIZONTAL:
        if isinstance(a, LineEntity):
            return np.array([a.y1 - a.y2], dtype=float)
        if isinstance(a, PointEntity) and isinstance(b, PointEntity):
            return np.array([a.y - b.y], dtype=float)
        return penalty

    if ctype == ConstraintType.VERTICAL:
        if isinstance(a, LineEntity):
            return np.array([a.x1 - a.x2], dtype=float)
        if isinstance(a, PointEntity) and isinstance(b, PointEntity):
            return np.array([a.x - b.x], dtype=float)
        return penalty

    if ctype == ConstraintType.PARALLEL:
        if isinstance(a, LineEntity) and isinstance(b, LineEntity):
            da = _line_direction(a)
            db = _line_direction(b)
            return np.array([_cross2d(da, db)], dtype=float)
        return penalty

    if ctype == ConstraintType.PERPENDICULAR:
        if isinstance(a, LineEntity) and isinstance(b, LineEntity):
            da = _line_direction(a)
            db = _line_direction(b)
            return np.array([np.dot(da, db)], dtype=float)
        return penalty

    if ctype == ConstraintType.EQUAL:
        if isinstance(a, LineEntity) and isinstance(b, LineEntity):
            return np.array([_line_length(a) - _line_length(b)], dtype=float)
        if isinstance(a, CircleEntity) and isinstance(b, CircleEntity):
            return np.array([a.radius - b.radius], dtype=float)
        if isinstance(a, RectangleEntity) and isinstance(b, RectangleEntity):
            return np.array([a.width - b.width, a.height - b.height], dtype=float)
        return penalty

    if ctype == ConstraintType.COINCIDENT:
        if isinstance(a, PointEntity) and isinstance(b, PointEntity):
            return np.array([a.x - b.x, a.y - b.y], dtype=float)
        if isinstance(a, PointEntity) and isinstance(b, LineEntity):
            return np.array([_point_line_distance(np.array([a.x, a.y], dtype=float), b)], dtype=float)
        if isinstance(a, LineEntity) and isinstance(b, PointEntity):
            return np.array([_point_line_distance(np.array([b.x, b.y], dtype=float), a)], dtype=float)
        return penalty

    if ctype == ConstraintType.TANGENT:
        if isinstance(a, CircleEntity) and isinstance(b, LineEntity):
            center = np.array([a.cx, a.cy], dtype=float)
            return np.array([_point_line_distance(center, b) - a.radius], dtype=float)
        if isinstance(a, LineEntity) and isinstance(b, CircleEntity):
            center = np.array([b.cx, b.cy], dtype=float)
            return np.array([_point_line_distance(center, a) - b.radius], dtype=float)
        if isinstance(a, CircleEntity) and isinstance(b, CircleEntity):
            d = float(np.linalg.norm(np.array([a.cx - b.cx, a.cy - b.cy], dtype=float)))
            return np.array([d - (a.radius + b.radius)], dtype=float)
        if isinstance(a, ArcEntity) and isinstance(b, LineEntity):
            center = np.array([a.cx, a.cy], dtype=float)
            return np.array([_point_line_distance(center, b) - a.radius], dtype=float)
        return penalty

    if ctype == ConstraintType.FIXED:
        initial = initial_params.get(constraint.a)
        if initial is None:
            return penalty
        current = np.array(_entity_to_params(a), dtype=float)
        return current - initial

    if ctype == ConstraintType.DISTANCE:
        if b is None or constraint.value is None:
            return penalty
        pa = _anchor(a)
        pb = _anchor(b)
        d = float(np.linalg.norm(pa - pb))
        return np.array([d - float(constraint.value)], dtype=float)

    if ctype == ConstraintType.ANGLE:
        if not isinstance(a, LineEntity) or not isinstance(b, LineEntity) or constraint.value is None:
            return penalty
        da = _line_direction(a)
        db = _line_direction(b)
        na = max(1e-12, float(np.linalg.norm(da)))
        nb = max(1e-12, float(np.linalg.norm(db)))
        cos_theta = float(np.clip(np.dot(da, db) / (na * nb), -1.0, 1.0))
        theta = float(np.arccos(cos_theta))
        return np.array([theta - float(constraint.value)], dtype=float)

    return penalty


def _all_residuals(
    entities: dict[str, Entity],
    initial_params: dict[str, np.ndarray],
    constraints: list[Constraint],
) -> tuple[np.ndarray, dict[str, float]]:
    pieces: list[np.ndarray] = []
    per_constraint: dict[str, float] = {}

    for constraint in constraints:
        residual = _constraint_residual(entities, initial_params, constraint)
        pieces.append(residual)
        per_constraint[constraint.id] = float(np.linalg.norm(residual))

    if not pieces:
        return np.array([], dtype=float), per_constraint

    return np.concatenate(pieces), per_constraint


def _numerical_jacobian(residual_fn: Callable[[np.ndarray], np.ndarray], x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    r0 = residual_fn(x)
    jac = np.zeros((r0.size, x.size), dtype=float)
    for idx in range(x.size):
        x_plus = x.copy()
        x_plus[idx] += eps
        x_minus = x.copy()
        x_minus[idx] -= eps
        jac[:, idx] = (residual_fn(x_plus) - residual_fn(x_minus)) / (2 * eps)
    return jac


def _gauss_newton(
    residual_fn: Callable[[np.ndarray], np.ndarray],
    x0: np.ndarray,
    max_iterations: int,
    tolerance: float,
) -> _OptimizeResult:
    x = x0.copy()
    damping = 1e-3
    prev_norm = float(np.linalg.norm(residual_fn(x)))

    for iteration in range(1, max_iterations + 1):
        r = residual_fn(x)
        jac = _numerical_jacobian(residual_fn, x)
        jt_j = jac.T @ jac
        rhs = jac.T @ r

        try:
            step = -np.linalg.solve(jt_j + damping * np.eye(x.size), rhs)
        except np.linalg.LinAlgError:
            step = -np.linalg.pinv(jt_j + damping * np.eye(x.size)) @ rhs

        if float(np.linalg.norm(step)) < tolerance:
            return _OptimizeResult(x=x, nit=iteration, success=True, message="Converged on small step.")

        trial = x + step
        trial_norm = float(np.linalg.norm(residual_fn(trial)))

        if trial_norm < prev_norm:
            x = trial
            prev_norm = trial_norm
            damping = max(1e-9, damping / 2)
        else:
            damping = min(1e3, damping * 2)

        if prev_norm < tolerance:
            return _OptimizeResult(x=x, nit=iteration, success=True, message="Converged on residual norm.")

    return _OptimizeResult(x=x, nit=max_iterations, success=False, message="Max iterations reached.")


def _minimize(
    residual_fn: Callable[[np.ndarray], np.ndarray],
    x0: np.ndarray,
    max_iterations: int,
    tolerance: float,
) -> _OptimizeResult:
    if scipy_minimize is not None:  # pragma: no cover - optional dependency path
        objective = lambda v: float(np.dot(residual_fn(v), residual_fn(v)))
        result = scipy_minimize(objective, x0, method="BFGS", options={"maxiter": max_iterations})
        return _OptimizeResult(
            x=np.array(result.x, dtype=float),
            nit=int(getattr(result, "nit", max_iterations)),
            success=bool(getattr(result, "success", False)),
            message=str(getattr(result, "message", "")),
        )
    return _gauss_newton(residual_fn, x0, max_iterations=max_iterations, tolerance=tolerance)


def _degrees_of_freedom(residual_fn: Callable[[np.ndarray], np.ndarray], x: np.ndarray) -> int:
    if x.size == 0:
        return 0
    residual = residual_fn(x)
    if residual.size == 0:
        return x.size
    jac = _numerical_jacobian(residual_fn, x)
    rank = int(np.linalg.matrix_rank(jac, tol=1e-6))
    return max(0, x.size - rank)


def _conflict_constraint(per_constraint: dict[str, float]) -> tuple[str | None, float]:
    if not per_constraint:
        return None, 0.0
    conflict = max(per_constraint.items(), key=lambda kv: kv[1])
    return conflict[0], float(conflict[1])


def _validate_constraint_references(sketch: Sketch) -> tuple[str | None, str | None]:
    entity_ids = set(sketch.entities.keys())
    requires_b = {
        ConstraintType.PARALLEL,
        ConstraintType.PERPENDICULAR,
        ConstraintType.EQUAL,
        ConstraintType.COINCIDENT,
        ConstraintType.TANGENT,
        ConstraintType.DISTANCE,
        ConstraintType.ANGLE,
    }
    requires_value = {ConstraintType.DISTANCE, ConstraintType.ANGLE}

    for constraint in sketch.constraints:
        if constraint.a not in entity_ids:
            return constraint.id, f"Constraint '{constraint.id}' references missing entity '{constraint.a}'."

        if constraint.b is not None and constraint.b not in entity_ids:
            return constraint.id, f"Constraint '{constraint.id}' references missing entity '{constraint.b}'."

        if constraint.type in requires_b and not constraint.b:
            return constraint.id, f"Constraint '{constraint.id}' of type '{constraint.type.value}' requires 'b'."

        if constraint.type in requires_value and constraint.value is None:
            return constraint.id, f"Constraint '{constraint.id}' of type '{constraint.type.value}' requires 'value'."

    return None, None


def solve_sketch(
    sketch: Sketch,
    max_iterations: int = 200,
    tolerance: float = 1e-6,
) -> SolveResult:
    validation_conflict_id, validation_message = _validate_constraint_references(sketch)
    if validation_message is not None:
        return SolveResult(
            status=SolveStatus.OVERCONSTRAINED,
            sketch=sketch,
            conflict_constraint_id=validation_conflict_id,
            max_residual=0.0,
            iterations=0,
            message=validation_message,
        )

    codec = _VectorCodec(sketch.entities)
    x0 = codec.to_vector(sketch.entities)

    initial_entities = codec.from_vector(x0, sketch.entities)
    initial_params = {
        entity_id: np.array(_entity_to_params(entity), dtype=float)
        for entity_id, entity in initial_entities.items()
    }

    if not sketch.constraints:
        return SolveResult(
            status=SolveStatus.UNDERCONSTRAINED,
            sketch=sketch,
            message="Sketch has no constraints.",
            iterations=0,
        )

    def residual_fn(vector: np.ndarray) -> np.ndarray:
        entities = codec.from_vector(vector, sketch.entities)
        residual, _ = _all_residuals(entities, initial_params, sketch.constraints)
        return residual

    opt = _minimize(residual_fn, x0, max_iterations=max_iterations, tolerance=tolerance)
    solved_entities = codec.from_vector(opt.x, sketch.entities)
    residual_vector, per_constraint = _all_residuals(solved_entities, initial_params, sketch.constraints)
    _, max_residual = _conflict_constraint(per_constraint)
    conflict_id, _ = _conflict_constraint(per_constraint)

    dof = _degrees_of_freedom(residual_fn, opt.x)

    if max_residual > tolerance * 10:
        status = SolveStatus.OVERCONSTRAINED
        message = "Constraints conflict or cannot be simultaneously satisfied."
    elif dof > 0:
        status = SolveStatus.UNDERCONSTRAINED
        conflict_id = None
        message = "Sketch has remaining degrees of freedom."
    else:
        status = SolveStatus.SOLVED
        conflict_id = None
        message = "Solved near initial position."

    solved_sketch = Sketch(entities=solved_entities, constraints=sketch.constraints)
    return SolveResult(
        status=status,
        sketch=solved_sketch,
        conflict_constraint_id=conflict_id if status == SolveStatus.OVERCONSTRAINED else None,
        max_residual=float(np.max(np.abs(residual_vector))) if residual_vector.size else 0.0,
        iterations=opt.nit,
        message=message,
    )


def check_sketch(sketch: Sketch, tolerance: float = 1e-6) -> CheckResult:
    validation_conflict_id, validation_message = _validate_constraint_references(sketch)
    if validation_message is not None:
        return CheckResult(
            status=SolveStatus.OVERCONSTRAINED,
            conflict_constraint_id=validation_conflict_id,
            max_residual=0.0,
            message=validation_message,
        )

    codec = _VectorCodec(sketch.entities)
    x0 = codec.to_vector(sketch.entities)
    initial_params = {
        entity_id: np.array(_entity_to_params(entity), dtype=float)
        for entity_id, entity in sketch.entities.items()
    }

    def residual_fn(vector: np.ndarray) -> np.ndarray:
        entities = codec.from_vector(vector, sketch.entities)
        residual, _ = _all_residuals(entities, initial_params, sketch.constraints)
        return residual

    residual_vector = residual_fn(x0)
    entities = codec.from_vector(x0, sketch.entities)
    _, per_constraint = _all_residuals(entities, initial_params, sketch.constraints)
    conflict_id, max_residual = _conflict_constraint(per_constraint)

    if max_residual > tolerance * 10:
        return CheckResult(
            status=SolveStatus.OVERCONSTRAINED,
            conflict_constraint_id=conflict_id,
            max_residual=max_residual,
            message="Current geometry violates one or more constraints.",
        )

    dof = _degrees_of_freedom(residual_fn, x0)
    if dof > 0:
        return CheckResult(
            status=SolveStatus.UNDERCONSTRAINED,
            max_residual=float(np.max(np.abs(residual_vector))) if residual_vector.size else 0.0,
            message="Constraint system has free degrees of freedom.",
        )

    return CheckResult(
        status=SolveStatus.SOLVED,
        max_residual=float(np.max(np.abs(residual_vector))) if residual_vector.size else 0.0,
        message="Constraint system is consistent and fully constrained.",
    )


# ── Variable / constraint mapping builders ──────────────────────────


_ENTITY_PARAM_NAMES: dict[type, list[str]] = {
    PointEntity: ["x", "y"],
    LineEntity: ["x1", "y1", "x2", "y2"],
    CircleEntity: ["cx", "cy", "radius"],
    ArcEntity: ["cx", "cy", "radius", "start_angle", "end_angle"],
    RectangleEntity: ["x", "y", "width", "height"],
}


def _build_variable_info(codec: _VectorCodec, entities: dict[str, Entity]) -> list[VariableInfo]:
    """Map every solver variable index back to its entity + parameter name."""
    info: list[VariableInfo] = []
    for entity_id in codec.order:
        start, end = codec.slices[entity_id]
        entity = entities[entity_id]
        names = _ENTITY_PARAM_NAMES.get(type(entity), [])
        for offset, name in enumerate(names):
            info.append(VariableInfo(index=start + offset, entity_id=entity_id, parameter_name=name))
    return info


def _build_constraint_info(
    entities: dict[str, Entity],
    initial_params: dict[str, np.ndarray],
    constraints: list[Constraint],
) -> list[ConstraintInfo]:
    """Map every constraint to its row span in the residual/Jacobian."""
    infos: list[ConstraintInfo] = []
    cursor = 0
    for constraint in constraints:
        residual = _constraint_residual(entities, initial_params, constraint)
        n = residual.size
        infos.append(ConstraintInfo(
            constraint_id=constraint.id,
            row_start=cursor,
            row_count=n,
            residual_norm=float(np.linalg.norm(residual)),
        ))
        cursor += n
    return infos


def _build_diagnostics(
    sketch: Sketch,
    codec: _VectorCodec,
    x: np.ndarray,
    initial_params: dict[str, np.ndarray],
    tolerance: float,
) -> ConstraintDiagnostics:
    """Compute full constraint-graph diagnostics for introspection."""
    entities = codec.from_vector(x, sketch.entities)

    # Variable info
    var_info = _build_variable_info(codec, sketch.entities)

    # Constraint info
    con_info = _build_constraint_info(entities, initial_params, sketch.constraints)

    # Residual function
    def residual_fn(vector: np.ndarray) -> np.ndarray:
        ents = codec.from_vector(vector, sketch.entities)
        residual, _ = _all_residuals(ents, initial_params, sketch.constraints)
        return residual

    residual = residual_fn(x)

    # Jacobian
    if x.size > 0 and residual.size > 0:
        jac = _numerical_jacobian(residual_fn, x)
        rank = int(np.linalg.matrix_rank(jac, tol=1e-6))
        # Sparse nonzero structure (row, col pairs where |J| > eps)
        nonzero = list(zip(*np.where(np.abs(jac) > 1e-8)))
        nonzero_entries = [(int(r), int(c)) for r, c in nonzero]
    else:
        jac = np.zeros((0, 0), dtype=float)
        rank = 0
        nonzero_entries = []

    jac_info = JacobianInfo(
        rows=int(jac.shape[0]) if jac.ndim == 2 else 0,
        cols=int(jac.shape[1]) if jac.ndim == 2 else 0,
        rank=rank,
        nonzero_entries=nonzero_entries,
    )

    dof = max(0, codec.dimension - rank)

    # Over-constrained identification: constraints with high residual
    _, per_constraint = _all_residuals(entities, initial_params, sketch.constraints)
    over_constrained_ids = [
        cid for cid, res in per_constraint.items() if res > tolerance * 10
    ]

    # Under-constrained variable identification via null space
    under_constrained_vars: list[int] = []
    if dof > 0 and jac.size > 0:
        # Variables not constrained: columns where all Jacobian entries are near-zero
        col_norms = np.linalg.norm(jac, axis=0)
        under_constrained_vars = [int(i) for i in range(col_norms.size) if col_norms[i] < 1e-8]

    # Determine status — check DOF first, then residual
    max_residual = float(np.max(np.abs(residual))) if residual.size else 0.0
    if dof > 0:
        status = SolveStatus.UNDERCONSTRAINED
    elif max_residual > tolerance * 10:
        status = SolveStatus.OVERCONSTRAINED
    else:
        status = SolveStatus.SOLVED

    return ConstraintDiagnostics(
        dof=dof,
        status=status,
        jacobian=jac_info,
        variables=var_info,
        constraints=con_info,
        over_constrained_ids=over_constrained_ids,
        under_constrained_variables=under_constrained_vars,
    )


def diagnose_sketch(sketch: Sketch, *, tolerance: float = 1e-6) -> ConstraintDiagnostics:
    """Public entry point for constraint-graph introspection."""
    validation_conflict_id, validation_message = _validate_constraint_references(sketch)
    if validation_message is not None:
        return ConstraintDiagnostics(
            dof=0,
            status=SolveStatus.OVERCONSTRAINED,
            jacobian=JacobianInfo(rows=0, cols=0, rank=0),
            over_constrained_ids=[validation_conflict_id] if validation_conflict_id else [],
        )

    codec = _VectorCodec(sketch.entities)
    x0 = codec.to_vector(sketch.entities)
    initial_params = {
        entity_id: np.array(_entity_to_params(entity), dtype=float)
        for entity_id, entity in sketch.entities.items()
    }
    return _build_diagnostics(sketch, codec, x0, initial_params, tolerance)


# ── PythonSolverBackend ─────────────────────────────────────────────


class PythonSolverBackend:
    """Built-in NumPy/SciPy Gauss-Newton constraint solver.

    Wraps the module-level ``solve_sketch``, ``check_sketch``, and
    ``diagnose_sketch`` functions as a :class:`SolverBackend` implementation.
    """

    @property
    def name(self) -> str:
        return "python"

    @property
    def supports_3d(self) -> bool:
        return False

    def solve(
        self,
        sketch: Sketch,
        *,
        max_iterations: int = 200,
        tolerance: float = 1e-6,
    ) -> SolveResult:
        result = solve_sketch(sketch, max_iterations=max_iterations, tolerance=tolerance)
        # Attach diagnostics to every solve result
        result.diagnostics = diagnose_sketch(sketch, tolerance=tolerance)
        return result

    def check(
        self,
        sketch: Sketch,
        *,
        tolerance: float = 1e-6,
    ) -> CheckResult:
        result = check_sketch(sketch, tolerance=tolerance)
        result.diagnostics = diagnose_sketch(sketch, tolerance=tolerance)
        return result

    def diagnose(
        self,
        sketch: Sketch,
        *,
        tolerance: float = 1e-6,
    ) -> ConstraintDiagnostics:
        return diagnose_sketch(sketch, tolerance=tolerance)
