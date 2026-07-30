from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

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


class MeshData(BaseModel):
    """Tessellated mesh representation — mirrors the frontend MeshPayload."""

    vertices: list[float] = Field(default_factory=list)
    faces: list[int] = Field(default_factory=list)
    normals: list[float] = Field(default_factory=list)


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
