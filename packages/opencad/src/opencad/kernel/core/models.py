from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, FiniteFloat, model_validator

from .errors import Failure


class BoundingBox(BaseModel):
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def volume(self) -> float:
        dx = max(0.0, self.max_x - self.min_x)
        dy = max(0.0, self.max_y - self.min_y)
        dz = max(0.0, self.max_z - self.min_z)
        return dx * dy * dz


class MeshFaceGroup(BaseModel):
    """Contiguous triangle-index range belonging to one modeling feature."""

    start: int
    count: int
    face_index: int
    owner_shape_id: str


class MeshData(BaseModel):
    """Tessellated mesh representation — mirrors the frontend MeshPayload."""

    vertices: list[float] = Field(default_factory=list)
    faces: list[int] = Field(default_factory=list)
    normals: list[float] = Field(default_factory=list)
    face_groups: list[MeshFaceGroup] = Field(default_factory=list)


# ── Topology naming ─────────────────────────────────────────────────


class SubshapeKind(str, Enum):
    FACE = "face"
    EDGE = "edge"


class SubshapeRef(BaseModel):
    """A stable reference to a topological sub-shape (face or edge)."""

    id: str  # e.g. "box-0001:face:0"
    kind: SubshapeKind
    index: int  # positional index in topology explorer
    centroid: tuple[float, float, float]
    normal: tuple[float, float, float] | None = None  # faces only
    area: float | None = None  # faces only
    length: float | None = None  # edges only
    tags: list[str] = Field(default_factory=list)  # e.g. ["top", "+Z"]


class TopologyMap(BaseModel):
    """Complete topology map for a shape — all faces and edges with stable refs."""

    shape_id: str
    faces: list[SubshapeRef] = Field(default_factory=list)
    edges: list[SubshapeRef] = Field(default_factory=list)


# ── Shape data ──────────────────────────────────────────────────────


class ShapeData(BaseModel):
    id: str
    kind: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    bbox: BoundingBox
    volume: float
    manifold: bool = True
    edge_ids: list[str] = Field(default_factory=list)
    face_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class Success(BaseModel):
    ok: bool = Field(default=True)
    shape_id: str | None = None
    shape: ShapeData | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


OperationResult = Success | Failure


# ── Assembly mates ──────────────────────────────────────────────────


class AssemblyMateStatus(str, Enum):
    PENDING = "pending"
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    ERROR = "error"


class AssemblyMate(BaseModel):
    """A 3-D assembly constraint between two entity references."""

    id: str
    type: str  # mirrors AssemblyMateType values
    entity_a: str
    entity_b: str
    value: float | None = None
    status: AssemblyMateStatus = AssemblyMateStatus.PENDING


# ── Rigid kinematics ────────────────────────────────────────────────


class KinematicJointType(str, Enum):
    FIXED = "fixed"
    REVOLUTE = "revolute"
    PRISMATIC = "prismatic"


class JointUnit(str, Enum):
    NONE = "none"
    RADIAN = "radian"
    MILLIMETER = "mm"


class RigidTransform(BaseModel):
    """Renderer-ready rigid transform in OpenCAD's native Z-up coordinates."""

    translation_mm: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (0.0, 0.0, 0.0)
    rotation_quaternion_xyzw: tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat] = (0.0, 0.0, 0.0, 1.0)

    @classmethod
    def identity(cls) -> "RigidTransform":
        return cls()


class KinematicJoint(BaseModel):
    """A rigid degree-of-freedom relationship between two shape occurrences.

    Revolute limits are radians. Prismatic limits are millimeters. Shape IDs
    act as occurrence IDs in this first contract; a future assembly-occurrence
    layer can replace them without changing pose evaluation.
    """

    id: str = Field(min_length=1)
    type: KinematicJointType
    parent_shape_id: str = Field(min_length=1)
    child_shape_id: str = Field(min_length=1)
    axis: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (0.0, 0.0, 1.0)
    origin_mm: tuple[FiniteFloat, FiniteFloat, FiniteFloat] = (0.0, 0.0, 0.0)
    lower_limit: FiniteFloat = 0.0
    upper_limit: FiniteFloat = 0.0
    unit: JointUnit = JointUnit.NONE
    label: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_joint(self) -> "KinematicJoint":
        if self.parent_shape_id == self.child_shape_id:
            raise ValueError("Kinematic joint parent and child must be different shapes.")
        if self.lower_limit > self.upper_limit:
            raise ValueError("Kinematic joint lower_limit must be <= upper_limit.")

        axis_length_sq = sum(component * component for component in self.axis)
        if self.type != KinematicJointType.FIXED and axis_length_sq <= 1e-24:
            raise ValueError("Kinematic joint axis must be non-zero.")

        expected_unit = {
            KinematicJointType.FIXED: JointUnit.NONE,
            KinematicJointType.REVOLUTE: JointUnit.RADIAN,
            KinematicJointType.PRISMATIC: JointUnit.MILLIMETER,
        }[self.type]
        self.unit = expected_unit

        if self.type == KinematicJointType.FIXED and (
            self.lower_limit != 0.0 or self.upper_limit != 0.0
        ):
            raise ValueError("Fixed joints must use zero lower/upper limits.")
        return self


class JointPose(BaseModel):
    joint_id: str
    child_shape_id: str
    progress: float
    value: float
    unit: JointUnit
    transform: RigidTransform
