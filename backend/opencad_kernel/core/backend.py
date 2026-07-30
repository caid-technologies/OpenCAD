"""KernelBackend Protocol — the swap boundary for geometry backends.

Any class implementing this protocol can serve as the geometry engine
behind OpenCadKernel.  Today: OCCT via CadQuery.  Tomorrow: Manifold,
libfive, or any other solid modelling library.

**v1 scope:** Capability parity with Build123d (loft, sweep, revolve,
shell, draft, chamfer, patterns, sketch ops, topology naming).
UX parity (workplanes, fluent builders, selector DSL) is a separate
milestone.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from opencad_kernel.core.models import MeshData, OperationResult, TopologyMap
from opencad_kernel.operations.schemas import (
    BooleanInput,
    ChamferEdgesInput,
    CircularPatternInput,
    CreateBoxInput,
    CreateConeInput,
    CreateCylinderInput,
    CreateSketchInput,
    CreateSphereInput,
    CreateTorusInput,
    DraftInput,
    ExportStlInput,
    ExportStepInput,
    ExtrudeInput,
    FilletEdgesInput,
    ImportStepInput,
    ImportStlInput,
    LinearPatternInput,
    LoftInput,
    MirrorInput,
    OffsetShapeInput,
    RevolveInput,
    ShellInput,
    SweepInput,
)


@runtime_checkable
class KernelBackend(Protocol):
    """Geometry backend protocol.

    Every method receives a validated Pydantic input model and returns
    an ``OperationResult`` (``Success | Failure``).  The backend owns its
    own shape storage (native handles + ShapeData metadata).
    """

    # ── Primitive creation ──────────────────────────────────────────

    def create_box(self, payload: CreateBoxInput) -> OperationResult: ...

    def create_cylinder(self, payload: CreateCylinderInput) -> OperationResult: ...

    def create_sphere(self, payload: CreateSphereInput) -> OperationResult: ...

    def create_cone(self, payload: CreateConeInput) -> OperationResult: ...

    def create_torus(self, payload: CreateTorusInput) -> OperationResult: ...

    # ── Booleans ────────────────────────────────────────────────────

    def boolean_union(self, payload: BooleanInput) -> OperationResult: ...

    def boolean_cut(self, payload: BooleanInput) -> OperationResult: ...

    def boolean_intersection(self, payload: BooleanInput) -> OperationResult: ...

    # ── Edge / face operations ──────────────────────────────────────

    def fillet_edges(self, payload: FilletEdgesInput) -> OperationResult: ...

    def chamfer_edges(self, payload: ChamferEdgesInput) -> OperationResult: ...

    def shell(self, payload: ShellInput) -> OperationResult: ...

    def draft(self, payload: DraftInput) -> OperationResult: ...

    def offset_shape(self, payload: OffsetShapeInput) -> OperationResult: ...

    # ── Sketch operations ───────────────────────────────────────────

    def create_sketch(self, payload: CreateSketchInput) -> OperationResult: ...

    def extrude(self, payload: ExtrudeInput) -> OperationResult: ...

    # ── Sweep / loft / revolve ──────────────────────────────────────

    def revolve(self, payload: RevolveInput) -> OperationResult: ...

    def sweep(self, payload: SweepInput) -> OperationResult: ...

    def loft(self, payload: LoftInput) -> OperationResult: ...

    # ── Patterns ────────────────────────────────────────────────────

    def linear_pattern(self, payload: LinearPatternInput) -> OperationResult: ...

    def circular_pattern(self, payload: CircularPatternInput) -> OperationResult: ...

    def mirror(self, payload: MirrorInput) -> OperationResult: ...

    # ── STEP I/O ────────────────────────────────────────────────────

    def import_step(self, payload: ImportStepInput) -> OperationResult: ...

    def export_step(self, payload: ExportStepInput) -> OperationResult: ...

    def import_stl(self, payload: ImportStlInput) -> OperationResult: ...

    def export_stl(self, payload: ExportStlInput) -> OperationResult: ...

    # ── Tessellation ────────────────────────────────────────────────

    def tessellate(self, shape_id: str, deflection: float = 0.1) -> MeshData: ...

    # ── Topology naming ─────────────────────────────────────────────

    def get_topology(self, shape_id: str) -> TopologyMap: ...

    # ── Escape hatch ────────────────────────────────────────────────

    def get_native_shape(self, shape_id: str) -> Any:
        """Return the native backend shape object (e.g. TopoDS_Shape).

        Returns ``None`` when not applicable.
        """
        ...

    # ── Store access ────────────────────────────────────────────────

    @property
    def store(self) -> Any:
        """Return the ShapeStore (or equivalent) held by this backend."""
        ...


@runtime_checkable
class StreamingMeshBackend(KernelBackend, Protocol):
    """Optional backend capability for face-by-face mesh streaming."""

    def tessellate_face(
        self,
        shape_id: str,
        face_index: int,
        deflection: float = 0.1,
    ) -> tuple[MeshData, int]: ...

    def count_faces(self, shape_id: str) -> int: ...
