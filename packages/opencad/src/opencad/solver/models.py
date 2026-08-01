from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class PointEntity(BaseModel):
    id: str
    type: Literal["point"] = "point"
    x: float
    y: float


class LineEntity(BaseModel):
    id: str
    type: Literal["line"] = "line"
    x1: float
    y1: float
    x2: float
    y2: float


class CircleEntity(BaseModel):
    id: str
    type: Literal["circle"] = "circle"
    cx: float
    cy: float
    radius: float


class ArcEntity(BaseModel):
    id: str
    type: Literal["arc"] = "arc"
    cx: float
    cy: float
    radius: float
    start_angle: float
    end_angle: float


class RectangleEntity(BaseModel):
    id: str
    type: Literal["rectangle"] = "rectangle"
    x: float
    y: float
    width: float
    height: float


Entity = Annotated[
    PointEntity | LineEntity | CircleEntity | ArcEntity | RectangleEntity,
    Field(discriminator="type"),
]


class ConstraintType(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    PARALLEL = "parallel"
    PERPENDICULAR = "perpendicular"
    EQUAL = "equal"
    COINCIDENT = "coincident"
    TANGENT = "tangent"
    FIXED = "fixed"
    DISTANCE = "distance"
    ANGLE = "angle"


class Constraint(BaseModel):
    id: str
    type: ConstraintType
    a: str
    b: str | None = None
    value: float | None = None


class Sketch(BaseModel):
    entities: dict[str, Entity]
    constraints: list[Constraint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_entity_ids(self) -> "Sketch":
        for key, entity in self.entities.items():
            if key != entity.id:
                raise ValueError(f"Entity key '{key}' must match entity.id '{entity.id}'.")
        return self


class SolveStatus(str, Enum):
    SOLVED = "SOLVED"
    OVERCONSTRAINED = "OVERCONSTRAINED"
    UNDERCONSTRAINED = "UNDERCONSTRAINED"


class SolveResult(BaseModel):
    status: SolveStatus
    sketch: Sketch
    conflict_constraint_id: str | None = None
    max_residual: float = 0.0
    iterations: int = 0
    message: str = ""
    diagnostics: "ConstraintDiagnostics | None" = None


class CheckResult(BaseModel):
    status: SolveStatus
    conflict_constraint_id: str | None = None
    max_residual: float = 0.0
    message: str = ""
    diagnostics: "ConstraintDiagnostics | None" = None


# ── Constraint-graph introspection ──────────────────────────────────


class VariableInfo(BaseModel):
    """Maps a solver variable index to the entity parameter it represents."""

    index: int
    entity_id: str
    parameter_name: str  # e.g. "x", "y", "radius", "x1", "start_angle"


class ConstraintInfo(BaseModel):
    """Maps constraint rows in the residual/Jacobian to a user constraint."""

    constraint_id: str
    row_start: int  # first row index in the Jacobian
    row_count: int  # number of residual rows this constraint contributes
    residual_norm: float = 0.0


class JacobianInfo(BaseModel):
    """Sparse Jacobian structure — shape, rank, and nonzero pattern."""

    rows: int  # total residual rows
    cols: int  # total variable columns
    rank: int
    nonzero_entries: list[tuple[int, int]] = []  # (row, col) pairs with |value| > eps


class ConstraintDiagnostics(BaseModel):
    """Full constraint-graph introspection payload.

    Exposes everything an AI agent or advanced user needs to reason about
    the geometric constraint system: remaining DOF, over/under-determined
    classification, per-constraint residuals, Jacobian sparsity, and
    variable ↔ constraint index mapping.
    """

    dof: int
    status: SolveStatus
    jacobian: JacobianInfo
    variables: list[VariableInfo] = []
    constraints: list[ConstraintInfo] = []
    over_constrained_ids: list[str] = []  # constraint IDs that conflict
    under_constrained_variables: list[int] = []  # variable indices with freedom
