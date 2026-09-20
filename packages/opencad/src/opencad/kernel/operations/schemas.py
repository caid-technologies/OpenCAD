from __future__ import annotations

from enum import Enum

from opencad.kernel.core.models import KinematicJointType
from pydantic import BaseModel, Field, FiniteFloat, field_validator, model_validator


# ── Primitives ──────────────────────────────────────────────────────


class CreateBoxInput(BaseModel):
    length: float
    width: float
    height: float


class CreateCylinderInput(BaseModel):
    radius: float
    height: float


class CreateSphereInput(BaseModel):
    radius: float


class CreateConeInput(BaseModel):
    radius1: float  # bottom radius
    radius2: float = 0.0  # top radius (0 = apex)
    height: float


class CreateTorusInput(BaseModel):
    major_radius: float
    minor_radius: float


# ── Placement ───────────────────────────────────────────────────────


class TranslateInput(BaseModel):
    shape_id: str = Field(min_length=1)
    offset: tuple[float, float, float]


# ── Booleans ────────────────────────────────────────────────────────


class BooleanInput(BaseModel):
    shape_a_id: str = Field(min_length=1)
    shape_b_id: str = Field(min_length=1)


# ── Edge / face operations ──────────────────────────────────────────


class FilletEdgesInput(BaseModel):
    shape_id: str = Field(min_length=1)
    edge_ids: list[str] = Field(default_factory=list)
    radius: float


class ChamferEdgesInput(BaseModel):
    shape_id: str = Field(min_length=1)
    edge_ids: list[str] = Field(default_factory=list)
    distance: float


class ShellInput(BaseModel):
    """Hollow-out a solid by removing listed faces and offsetting inward."""

    shape_id: str = Field(min_length=1)
    face_ids: list[str] = Field(default_factory=list)
    thickness: float


class DraftInput(BaseModel):
    """Taper selected faces about a world-space neutral plane.

    Angles are signed degrees. By default the plane passes through the world
    origin and is perpendicular to the pull direction. Its intersection with
    each selected face remains fixed. For sides initially parallel to the pull
    axis, positive angles taper inward on the pull side and negative outward.
    """

    shape_id: str = Field(min_length=1)
    face_ids: list[str]
    angle: FiniteFloat  # signed degrees; backend validates the supported range
    pull_direction: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (0.0, 0.0, 1.0)
    neutral_plane_origin: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = Field(
        default=(0.0, 0.0, 0.0), description="Point on the neutral plane in world coordinates.",
    )
    neutral_plane_normal: tuple[FiniteFloat, FiniteFloat, FiniteFloat] | None = Field(
        default=None, description="World-space plane normal; omitted/null uses pull_direction.",
    )

    @field_validator("pull_direction", "neutral_plane_normal")
    @classmethod
    def nonzero_direction(
        cls, value: tuple[float, float, float] | None,
    ) -> tuple[float, float, float] | None:
        if value is not None and not any(value):
            raise ValueError("Draft directions must be non-zero.")
        return value


class OffsetShapeInput(BaseModel):
    shape_id: str = Field(min_length=1)
    distance: float


# ── Sketch operations ──────────────────────────────────────────────


class SketchSegment(BaseModel):
    """A single 2-D sketch element."""

    type: str  # "line" | "arc" | "circle"
    start: tuple[float, float] | None = None
    end: tuple[float, float] | None = None
    center: tuple[float, float] | None = None
    radius: float | None = None
    subtract: bool = False


class CreateSketchInput(BaseModel):
    """Construct a 2-D wire profile from line/arc/circle segments."""

    plane: str = "XY"  # XY, XZ, YZ
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    segments: list[SketchSegment] = Field(default_factory=list)


class ExtrudeInput(BaseModel):
    sketch_id: str = Field(min_length=1)
    distance: float
    both: bool = False


# ── Sweep / loft / revolve ──────────────────────────────────────────


class RevolveInput(BaseModel):
    """Revolve a profile (wire/sketch) around an axis."""

    shape_id: str = Field(min_length=1)
    axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    angle: float = 360.0  # degrees


class SweepInput(BaseModel):
    """Sweep a profile along a path wire."""

    profile_id: str = Field(min_length=1)
    path_id: str = Field(min_length=1)


class LoftInput(BaseModel):
    """Loft through an ordered list of profiles."""

    profile_ids: list[str] = Field(min_length=2)
    solid: bool = True
    ruled: bool = False


# ── Patterns ────────────────────────────────────────────────────────


class LinearPatternInput(BaseModel):
    shape_id: str = Field(min_length=1)
    direction: tuple[float, float, float]
    count: int = Field(ge=2)
    spacing: float


class CircularPatternInput(BaseModel):
    shape_id: str = Field(min_length=1)
    axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    count: int = Field(ge=2)
    angle: float = 360.0  # total angular span in degrees


class MirrorInput(BaseModel):
    shape_id: str = Field(min_length=1)
    plane_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    plane_normal: tuple[float, float, float] = (1.0, 0.0, 0.0)


# ── STEP I/O ────────────────────────────────────────────────────────


class ImportStepInput(BaseModel):
    filepath: str = Field(min_length=1)


class ExportStepInput(BaseModel):
    shape_id: str = Field(min_length=1)
    filepath: str = Field(min_length=1)


class ImportStlInput(BaseModel):
    filepath: str = Field(min_length=1)


class ExportStlInput(BaseModel):
    shape_id: str = Field(min_length=1)
    filepath: str = Field(min_length=1)


# ── Assembly mates (3-D constraints — Phase 1) ────────────────────


class AssemblyMateType(str, Enum):
    """Supported assembly mate constraint types.

    Each mate restricts degrees of freedom between two entity references
    (shape faces, edges, or origins).
    """

    COINCIDENT = "coincident"  # two faces flush / coplanar
    CONCENTRIC = "concentric"  # two cylindrical faces share axis
    DISTANCE = "distance"  # faces offset by a scalar value
    ANGLE = "angle"  # faces at an angular offset (radians)
    PARALLEL = "parallel"  # face normals aligned
    PERPENDICULAR = "perpendicular"  # face normals at 90°


class CreateAssemblyMateInput(BaseModel):
    """Create a 3-D assembly mate between two entity references.

    Entity references use the ``shape_id:face:N`` or ``shape_id:edge:N``
    naming convention already established by the topology module.
    """

    type: AssemblyMateType
    entity_a: str = Field(min_length=1, description="First entity reference (e.g. 'box-0001:face:0')")
    entity_b: str = Field(min_length=1, description="Second entity reference")
    value: float | None = Field(default=None, description="Numeric value for distance/angle mates")


class DeleteAssemblyMateInput(BaseModel):
    mate_id: str = Field(min_length=1)


class ListAssemblyMatesInput(BaseModel):
    """Optionally filter by entity involvement."""

    entity_ref: str | None = None


# ── Rigid kinematic joints ─────────────────────────────────────────


class CreateKinematicJointInput(BaseModel):
    """Create one rigid DOF relationship between two shape occurrences.

    Revolute limits are radians; prismatic limits are millimeters.
    """

    type: KinematicJointType
    joint_id: str | None = Field(default=None, min_length=1)
    parent_shape_id: str = Field(min_length=1)
    child_shape_id: str = Field(min_length=1)
    axis: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (0.0, 0.0, 1.0)
    origin_mm: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (0.0, 0.0, 0.0)
    lower_limit: FiniteFloat = 0.0
    upper_limit: FiniteFloat = 0.0
    label: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_joint(self) -> "CreateKinematicJointInput":
        if self.parent_shape_id == self.child_shape_id:
            raise ValueError("Kinematic joint parent and child must be different shapes.")
        if self.lower_limit > self.upper_limit:
            raise ValueError("lower_limit must be <= upper_limit.")
        if self.type != KinematicJointType.FIXED and not any(self.axis):
            raise ValueError("Movable kinematic joints require a non-zero axis.")
        if self.type == KinematicJointType.FIXED and (
            self.lower_limit != 0.0 or self.upper_limit != 0.0
        ):
            raise ValueError("Fixed joints must use zero limits.")
        return self


class DeleteKinematicJointInput(BaseModel):
    joint_id: str = Field(min_length=1)


class ListKinematicJointsInput(BaseModel):
    shape_id: str | None = None


class EvaluateKinematicJointInput(BaseModel):
    joint_id: str = Field(min_length=1)
    progress: FiniteFloat = Field(default=0.0, ge=0.0, le=1.0)


class EvaluateKinematicAssemblyInput(BaseModel):
    progress_by_joint: dict[str, FiniteFloat] = Field(default_factory=dict)

    @field_validator("progress_by_joint")
    @classmethod
    def normalized_progress(cls, value: dict[str, float]) -> dict[str, float]:
        for joint_id, progress in value.items():
            if progress < 0.0 or progress > 1.0:
                raise ValueError(
                    f"Joint progress for '{joint_id}' must be between 0 and 1."
                )
        return value


# ── Topology selectors ─────────────────────────────────────────────


class SelectorQuery(BaseModel):
    """Query to select subshapes by geometric / tag criteria."""

    kind: str = "face"  # "face" | "edge"
    direction: tuple[float, float, float] | None = None
    direction_tolerance: float = 0.1  # cosine distance
    near_point: tuple[float, float, float] | None = None
    near_tolerance: float = 1.0
    min_area: float | None = None
    max_area: float | None = None
    tags: list[str] | None = None
    sort_by: str | None = None  # "x" | "y" | "z" | "area" | "length"
    sort_reverse: bool = False
    limit: int | None = None
