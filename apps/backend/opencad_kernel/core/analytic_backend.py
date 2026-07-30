from __future__ import annotations

import json
import math
import struct
from math import pow
from pathlib import Path
from typing import Any, Literal

from opencad_kernel.core.checks import check_bbox_overlap, check_manifold, check_nonzero_volume
from opencad_kernel.core.errors import ErrorCode, make_failure
from opencad_kernel.core.geometry import (
    box_bbox,
    box_volume,
    cylinder_bbox,
    cylinder_volume,
    overlap_bbox,
    overlap_volume,
    sphere_bbox,
    sphere_volume,
    union_bbox,
)
from opencad_kernel.core.models import (
    BoundingBox,
    MeshData,
    OperationResult,
    ShapeData,
    Success,
    TopologyMap,
)
from opencad_kernel.core.store import IdStrategy, ShapeStore
from opencad_kernel.core.topology import build_synthetic_topology
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

BooleanOp = Literal["boolean_union", "boolean_cut", "boolean_intersection"]


def _read_stl_vertices(filepath: Path) -> list[tuple[float, float, float]]:
    data = filepath.read_bytes()
    vertices: list[tuple[float, float, float]] = []

    if data.lstrip().lower().startswith(b"solid"):
        for line in data.decode("utf-8", errors="ignore").splitlines():
            fields = line.strip().split()
            if len(fields) == 4 and fields[0].lower() == "vertex":
                vertices.append((float(fields[1]), float(fields[2]), float(fields[3])))
        if vertices:
            return vertices

    if len(data) < 84:
        raise ValueError("STL file is too short.")
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    expected_size = 84 + triangle_count * 50
    if len(data) < expected_size:
        raise ValueError("Binary STL triangle data is truncated.")
    for triangle_index in range(triangle_count):
        offset = 84 + triangle_index * 50 + 12
        coordinates = struct.unpack_from("<9f", data, offset)
        vertices.extend(
            (coordinates[index], coordinates[index + 1], coordinates[index + 2])
            for index in range(0, 9, 3)
        )
    return vertices


def _triangle_normal(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def _bbox_stl(shape: ShapeData) -> str:
    box = shape.bbox
    points = [
        (box.min_x, box.min_y, box.min_z),
        (box.max_x, box.min_y, box.min_z),
        (box.max_x, box.max_y, box.min_z),
        (box.min_x, box.max_y, box.min_z),
        (box.min_x, box.min_y, box.max_z),
        (box.max_x, box.min_y, box.max_z),
        (box.max_x, box.max_y, box.max_z),
        (box.min_x, box.max_y, box.max_z),
    ]
    triangles = [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ]
    lines = ["solid opencad"]
    for first, second, third in triangles:
        a, b, c = points[first], points[second], points[third]
        normal = _triangle_normal(a, b, c)
        lines.append(f"  facet normal {normal[0]} {normal[1]} {normal[2]}")
        lines.append("    outer loop")
        for vertex in (a, b, c):
            lines.append(f"      vertex {vertex[0]} {vertex[1]} {vertex[2]}")
        lines.extend(("    endloop", "  endfacet"))
    lines.append("endsolid opencad")
    return "\n".join(lines) + "\n"


class AnalyticBackend:
    """Lightweight metadata-only geometry backend.

    This backend intentionally approximates geometry with bounding boxes and
    analytic measurements. It exists for tests and environments where OCCT is
    unavailable; production geometry should use :class:`OcctBackend`.
    """

    def __init__(
        self,
        tolerance: float = 1e-6,
        allow_partial_boolean: bool = False,
        id_strategy: IdStrategy = "uuid",
    ) -> None:
        self.tolerance = tolerance
        self.allow_partial_boolean = allow_partial_boolean
        self.store = ShapeStore(id_strategy=id_strategy)

    def _invalid_input(self, message: str) -> OperationResult:
        return make_failure(
            code=ErrorCode.INVALID_INPUT,
            message=message,
            suggestion="Review numeric inputs and try again.",
            failed_check="input_validation",
        )

    def _shape_not_found(self, shape_id: str) -> OperationResult:
        return make_failure(
            code=ErrorCode.SHAPE_NOT_FOUND,
            message=f"Shape '{shape_id}' was not found.",
            suggestion="Use an existing shape_id from a previous successful operation.",
            failed_check="shape_lookup",
        )

    def _success(self, shape: ShapeData, operation: str, **metadata: object) -> Success:
        self.store.add(shape)
        return Success(shape_id=shape.id, shape=shape, metadata={"operation": operation, **metadata})

    def _make_shape(
        self,
        kind: str,
        bbox: BoundingBox,
        volume: float,
        parameters: dict[str, object],
        manifold: bool = True,
        edge_count: int = 0,
        face_count: int = 0,
        source_ids: list[str] | None = None,
    ) -> ShapeData:
        shape_id = self.store.new_id(kind)
        edges = [f"{shape_id}:edge:{idx}" for idx in range(edge_count)]
        faces = [f"{shape_id}:face:{idx}" for idx in range(face_count)]
        return ShapeData(
            id=shape_id,
            kind=kind,
            parameters=parameters,
            bbox=bbox,
            volume=volume,
            manifold=manifold,
            edge_ids=edges,
            face_ids=faces,
            source_ids=source_ids or [],
        )

    def create_box(self, payload: CreateBoxInput) -> OperationResult:
        if payload.length <= self.tolerance or payload.width <= self.tolerance or payload.height <= self.tolerance:
            return self._invalid_input("Box dimensions must be greater than tolerance.")

        shape = self._make_shape(
            kind="box",
            bbox=box_bbox(payload.length, payload.width, payload.height),
            volume=box_volume(payload.length, payload.width, payload.height),
            parameters=payload.model_dump(),
            edge_count=12,
            face_count=6,
        )
        return self._success(shape, "create_box")

    def create_cylinder(self, payload: CreateCylinderInput) -> OperationResult:
        if payload.radius <= self.tolerance or payload.height <= self.tolerance:
            return self._invalid_input("Cylinder radius and height must be greater than tolerance.")

        shape = self._make_shape(
            kind="cylinder",
            bbox=cylinder_bbox(payload.radius, payload.height),
            volume=cylinder_volume(payload.radius, payload.height),
            parameters=payload.model_dump(),
            edge_count=3,
            face_count=3,
        )
        return self._success(shape, "create_cylinder")

    def create_sphere(self, payload: CreateSphereInput) -> OperationResult:
        if payload.radius <= self.tolerance:
            return self._invalid_input("Sphere radius must be greater than tolerance.")

        shape = self._make_shape(
            kind="sphere",
            bbox=sphere_bbox(payload.radius),
            volume=sphere_volume(payload.radius),
            parameters=payload.model_dump(),
            edge_count=1,
            face_count=1,
        )
        return self._success(shape, "create_sphere")

    def _fetch_shape_pair(self, payload: BooleanInput) -> tuple[ShapeData, ShapeData] | OperationResult:
        shape_a = self.store.get(payload.shape_a_id)
        if not shape_a:
            return self._shape_not_found(payload.shape_a_id)

        shape_b = self.store.get(payload.shape_b_id)
        if not shape_b:
            return self._shape_not_found(payload.shape_b_id)

        return shape_a, shape_b

    def _preflight_boolean(
        self,
        op_name: BooleanOp,
        shape_a: ShapeData,
        shape_b: ShapeData,
    ) -> OperationResult | None:
        volume_a = check_nonzero_volume(shape_a, self.tolerance)
        if volume_a:
            return volume_a

        volume_b = check_nonzero_volume(shape_b, self.tolerance)
        if volume_b:
            return volume_b

        manifold_a = check_manifold(shape_a)
        if manifold_a:
            return manifold_a

        manifold_b = check_manifold(shape_b)
        if manifold_b:
            return manifold_b

        if op_name in {"boolean_union", "boolean_intersection"}:
            overlap = check_bbox_overlap(shape_a, shape_b, self.tolerance)
            if overlap:
                return overlap

        return None

    def _run_boolean(self, op_name: BooleanOp, shape_a: ShapeData, shape_b: ShapeData) -> OperationResult:
        bbox_overlap = overlap_volume(shape_a.bbox, shape_b.bbox)
        estimated_overlap = min(bbox_overlap, shape_a.volume, shape_b.volume)

        if op_name == "boolean_union":
            result_volume = shape_a.volume + shape_b.volume - estimated_overlap
            result_bbox = union_bbox(shape_a.bbox, shape_b.bbox)

        elif op_name == "boolean_cut":
            result_volume = shape_a.volume - estimated_overlap
            if result_volume <= self.tolerance:
                return make_failure(
                    code=ErrorCode.ZERO_VOLUME,
                    message="Boolean cut removed all material from the base shape.",
                    suggestion="Reduce overlap or choose a different cutting shape.",
                    failed_check="boolean_result_volume",
                )
            result_bbox = shape_a.bbox

        else:  # boolean_intersection
            result_volume = estimated_overlap
            if result_volume <= self.tolerance:
                return make_failure(
                    code=ErrorCode.BBOX_NEAR_TANGENT,
                    message="Intersection produced near-zero volume.",
                    suggestion="Increase overlap between shapes before intersection.",
                    failed_check="boolean_result_volume",
                )
            result_bbox = overlap_bbox(shape_a.bbox, shape_b.bbox)

        result = self._make_shape(
            kind=op_name,
            bbox=result_bbox,
            volume=result_volume,
            parameters={"shape_a_id": shape_a.id, "shape_b_id": shape_b.id},
            edge_count=max(1, len(shape_a.edge_ids) + len(shape_b.edge_ids)),
            source_ids=[shape_a.id, shape_b.id],
        )
        return self._success(result, op_name, preflight="passed")

    def _boolean(self, op_name: BooleanOp, payload: BooleanInput) -> OperationResult:
        pair = self._fetch_shape_pair(payload)
        if not isinstance(pair, tuple):
            return pair

        shape_a, shape_b = pair
        preflight = self._preflight_boolean(op_name, shape_a, shape_b)
        if preflight is not None:
            return preflight

        try:
            return self._run_boolean(op_name, shape_a, shape_b)
        except Exception as exc:  # pragma: no cover
            return make_failure(
                code=ErrorCode.BOOLEAN_KERNEL_ERROR,
                message=f"Boolean operation failed: {exc}",
                suggestion="Inspect input geometry and retry with cleaned shapes.",
                failed_check="kernel_execution",
            )

    def boolean_union(self, payload: BooleanInput) -> OperationResult:
        return self._boolean("boolean_union", payload)

    def boolean_cut(self, payload: BooleanInput) -> OperationResult:
        return self._boolean("boolean_cut", payload)

    def boolean_intersection(self, payload: BooleanInput) -> OperationResult:
        return self._boolean("boolean_intersection", payload)

    def fillet_edges(self, payload: FilletEdgesInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)

        if not payload.edge_ids:
            return self._invalid_input("At least one edge_id is required for fillet.")
        if payload.radius <= self.tolerance:
            return self._invalid_input("Fillet radius must be greater than tolerance.")

        dx = shape.bbox.max_x - shape.bbox.min_x
        dy = shape.bbox.max_y - shape.bbox.min_y
        dz = shape.bbox.max_z - shape.bbox.min_z
        max_radius = max(self.tolerance, min(dx, dy, dz) / 2.0)
        if payload.radius >= max_radius:
            return make_failure(
                code=ErrorCode.FILLET_RADIUS_TOO_LARGE,
                message=f"Fillet radius {payload.radius} exceeds max allowed {max_radius:.6f}.",
                suggestion="Reduce fillet radius or increase base feature size.",
                failed_check="fillet_radius",
            )

        reduction = min(0.5, 0.02 * len(payload.edge_ids))
        shape_out = self._make_shape(
            kind="fillet",
            bbox=shape.bbox,
            volume=max(self.tolerance, shape.volume * (1.0 - reduction)),
            parameters={"shape_id": payload.shape_id, "edge_ids": payload.edge_ids, "radius": payload.radius},
            edge_count=max(1, len(shape.edge_ids)),
            source_ids=[shape.id],
        )
        return self._success(shape_out, "fillet_edges")

    def offset_shape(self, payload: OffsetShapeInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)

        dx = shape.bbox.max_x - shape.bbox.min_x
        dy = shape.bbox.max_y - shape.bbox.min_y
        dz = shape.bbox.max_z - shape.bbox.min_z
        if payload.distance < 0 and (dx + (2 * payload.distance) <= self.tolerance or dy + (2 * payload.distance) <= self.tolerance or dz + (2 * payload.distance) <= self.tolerance):
            return make_failure(
                code=ErrorCode.OFFSET_COLLAPSE,
                message="Negative offset collapses the shape.",
                suggestion="Use a smaller negative offset or a positive offset.",
                failed_check="offset_validity",
            )

        out_bbox = BoundingBox(
            min_x=shape.bbox.min_x - payload.distance,
            min_y=shape.bbox.min_y - payload.distance,
            min_z=shape.bbox.min_z - payload.distance,
            max_x=shape.bbox.max_x + payload.distance,
            max_y=shape.bbox.max_y + payload.distance,
            max_z=shape.bbox.max_z + payload.distance,
        )

        out_shape = self._make_shape(
            kind="offset",
            bbox=out_bbox,
            volume=max(self.tolerance, out_bbox.volume()),
            parameters={"shape_id": payload.shape_id, "distance": payload.distance},
            edge_count=max(1, len(shape.edge_ids)),
            source_ids=[shape.id],
        )
        return self._success(out_shape, "offset_shape")

    def import_step(self, payload: ImportStepInput) -> OperationResult:
        filepath = Path(payload.filepath)
        if filepath.suffix.lower() not in {".step", ".stp"}:
            return make_failure(
                code=ErrorCode.UNSUPPORTED_STEP,
                message="Only .step and .stp files are supported.",
                suggestion="Convert the source file to STEP format.",
                failed_check="step_extension",
            )

        try:
            text = filepath.read_text(encoding="utf-8")
        except OSError as exc:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message=f"Failed to read STEP file: {exc}",
                suggestion="Verify file path and read permissions.",
                failed_check="step_io",
            )

        parsed: dict[str, object] = {}
        lines = text.splitlines()
        if lines and lines[0].strip() == "OPENCAD-MOCK" and len(lines) > 1:
            try:
                parsed = json.loads(lines[1])
            except json.JSONDecodeError:
                parsed = {}

        if "bbox" in parsed and isinstance(parsed["bbox"], dict):
            bbox = BoundingBox.model_validate(parsed["bbox"])
            volume = float(parsed.get("volume", bbox.volume()))
        else:
            approx_volume = max(1.0, len(text) * 1e-3)
            side = pow(approx_volume, 1.0 / 3.0)
            bbox = BoundingBox(min_x=0.0, min_y=0.0, min_z=0.0, max_x=side, max_y=side, max_z=side)
            volume = approx_volume

        shape = self._make_shape(
            kind="imported_step",
            bbox=bbox,
            volume=volume,
            parameters={"filepath": payload.filepath},
            edge_count=12,
        )
        return self._success(shape, "import_step", imported_from=payload.filepath)

    def export_step(self, payload: ExportStepInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)

        return make_failure(
            code=ErrorCode.UNSUPPORTED_STEP,
            message="The analytic backend cannot export STEP geometry.",
            suggestion="Use the OCCT backend and install it with: uv sync --extra occt",
            failed_check="native_geometry_backend",
        )

    def import_stl(self, payload: ImportStlInput) -> OperationResult:
        filepath = Path(payload.filepath)
        if filepath.suffix.lower() != ".stl":
            return make_failure(
                code=ErrorCode.UNSUPPORTED_FILE_FORMAT,
                message="STL import requires a .stl file.",
                suggestion="Choose an STL file.",
                failed_check="stl_extension",
            )
        try:
            vertices = _read_stl_vertices(filepath)
        except (OSError, ValueError, struct.error) as exc:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message=f"Failed to read STL file: {exc}",
                suggestion="Verify that the file is a valid ASCII or binary STL.",
                failed_check="stl_io",
            )
        if len(vertices) < 3:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message="STL file contains no triangles.",
                suggestion="Choose a non-empty STL file.",
                failed_check="stl_geometry",
            )
        xs, ys, zs = zip(*vertices)
        bbox = BoundingBox(
            min_x=min(xs), min_y=min(ys), min_z=min(zs),
            max_x=max(xs), max_y=max(ys), max_z=max(zs),
        )
        shape = self._make_shape(
            kind="imported_stl",
            bbox=bbox,
            volume=max(self.tolerance, bbox.volume()),
            parameters={"filepath": payload.filepath},
            edge_count=len(vertices),
            face_count=len(vertices) // 3,
        )
        return self._success(shape, "import_stl", imported_from=payload.filepath)

    def export_stl(self, payload: ExportStlInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)
        filepath = Path(payload.filepath)
        if filepath.suffix.lower() != ".stl":
            return make_failure(
                code=ErrorCode.UNSUPPORTED_FILE_FORMAT,
                message="STL export requires a .stl destination.",
                suggestion="Use a filename ending in .stl.",
                failed_check="stl_extension",
            )
        try:
            filepath.write_text(_bbox_stl(shape), encoding="utf-8")
        except OSError as exc:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message=f"Failed to write STL file: {exc}",
                suggestion="Verify destination directory permissions.",
                failed_check="stl_io",
            )
        return Success(shape_id=shape.id, shape=None, metadata={"operation": "export_stl", "filepath": payload.filepath})

    # ── Tessellation (delegates to backend) ─────────────────────────

    def tessellate(self, shape_id: str, deflection: float = 0.1) -> MeshData:
        """Tessellate the shape identified by *shape_id*.

        Requires an OCCT (or other tessellation-capable) backend.
        The analytic fallback kernel cannot produce mesh data.
        """
        raise NotImplementedError(
            "Tessellation requires an OCCT backend.  "
            "Start the kernel with OPENCAD_KERNEL_BACKEND=occt."
        )

    def get_native_shape(self, shape_id: str) -> Any:
        return None

    # ── Additional primitives ───────────────────────────────────────

    def create_cone(self, payload: CreateConeInput) -> OperationResult:
        if payload.height <= self.tolerance:
            return self._invalid_input("Cone height must be greater than tolerance.")
        if payload.radius1 <= self.tolerance and payload.radius2 <= self.tolerance:
            return self._invalid_input("At least one cone radius must be greater than tolerance.")

        r1, r2, h = payload.radius1, payload.radius2, payload.height
        r_max = max(r1, r2)
        vol = (math.pi * h / 3.0) * (r1 ** 2 + r2 ** 2 + r1 * r2)
        bbox = BoundingBox(min_x=-r_max, min_y=-r_max, min_z=0.0, max_x=r_max, max_y=r_max, max_z=h)
        shape = self._make_shape("cone", bbox, vol, payload.model_dump(), edge_count=3, face_count=3)
        return self._success(shape, "create_cone")

    def create_torus(self, payload: CreateTorusInput) -> OperationResult:
        if payload.major_radius <= self.tolerance or payload.minor_radius <= self.tolerance:
            return self._invalid_input("Torus radii must be greater than tolerance.")
        if payload.minor_radius >= payload.major_radius:
            return self._invalid_input("Minor radius must be less than major radius.")

        R, r = payload.major_radius, payload.minor_radius
        vol = 2 * math.pi ** 2 * R * r ** 2
        outer = R + r
        bbox = BoundingBox(min_x=-outer, min_y=-outer, min_z=-r, max_x=outer, max_y=outer, max_z=r)
        shape = self._make_shape("torus", bbox, vol, payload.model_dump(), edge_count=2, face_count=1)
        return self._success(shape, "create_torus")

    # ── Chamfer ─────────────────────────────────────────────────────

    def chamfer_edges(self, payload: ChamferEdgesInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)
        if not payload.edge_ids:
            return self._invalid_input("At least one edge_id is required for chamfer.")
        if payload.distance <= self.tolerance:
            return self._invalid_input("Chamfer distance must be greater than tolerance.")

        reduction = min(0.5, 0.015 * len(payload.edge_ids))
        shape_out = self._make_shape(
            kind="chamfer",
            bbox=shape.bbox,
            volume=max(self.tolerance, shape.volume * (1.0 - reduction)),
            parameters={"shape_id": payload.shape_id, "edge_ids": payload.edge_ids, "distance": payload.distance},
            edge_count=max(1, len(shape.edge_ids) + len(payload.edge_ids)),
            face_count=max(1, len(shape.face_ids) + len(payload.edge_ids)),
            source_ids=[shape.id],
        )
        return self._success(shape_out, "chamfer_edges")

    # ── Shell ───────────────────────────────────────────────────────

    def shell(self, payload: ShellInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)
        if payload.thickness <= self.tolerance:
            return self._invalid_input("Shell thickness must be greater than tolerance.")

        # Heuristic: shell removes volume proportional to thickness
        dx = shape.bbox.max_x - shape.bbox.min_x
        dy = shape.bbox.max_y - shape.bbox.min_y
        dz = shape.bbox.max_z - shape.bbox.min_z
        inner_vol = max(0.0, (dx - 2 * payload.thickness) * (dy - 2 * payload.thickness) * (dz - 2 * payload.thickness))
        if inner_vol <= self.tolerance:
            return make_failure(
                code=ErrorCode.SHELL_FAILURE,
                message="Shell thickness too large — would consume entire solid.",
                suggestion="Reduce shell thickness.",
                failed_check="shell_validity",
            )

        shell_vol = shape.volume - inner_vol
        shape_out = self._make_shape(
            kind="shell",
            bbox=shape.bbox,
            volume=max(self.tolerance, shell_vol),
            parameters={"shape_id": payload.shape_id, "face_ids": payload.face_ids, "thickness": payload.thickness},
            edge_count=max(1, len(shape.edge_ids) * 2),
            face_count=max(1, len(shape.face_ids) * 2 - len(payload.face_ids)),
            source_ids=[shape.id],
        )
        return self._success(shape_out, "shell")

    # ── Draft ───────────────────────────────────────────────────────

    def draft(self, payload: DraftInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)
        if not payload.face_ids:
            return self._invalid_input("At least one face_id is required for draft.")
        if abs(payload.angle) <= self.tolerance:
            return self._invalid_input("Draft angle must be non-zero.")
        if abs(payload.angle) >= 90.0:
            return self._invalid_input("Draft angle must be less than 90 degrees.")

        # Draft slightly expands bbox
        tan_a = math.tan(math.radians(abs(payload.angle)))
        expand = tan_a * (shape.bbox.max_z - shape.bbox.min_z) * 0.5
        draft_bbox = BoundingBox(
            min_x=shape.bbox.min_x - expand, min_y=shape.bbox.min_y - expand, min_z=shape.bbox.min_z,
            max_x=shape.bbox.max_x + expand, max_y=shape.bbox.max_y + expand, max_z=shape.bbox.max_z,
        )
        shape_out = self._make_shape(
            kind="draft",
            bbox=draft_bbox,
            volume=max(self.tolerance, shape.volume * (1.0 + 0.01 * abs(payload.angle))),
            parameters=payload.model_dump(),
            edge_count=max(1, len(shape.edge_ids)),
            face_count=max(1, len(shape.face_ids)),
            source_ids=[shape.id],
        )
        return self._success(shape_out, "draft")

    # ── Sketch operations ───────────────────────────────────────────

    def create_sketch(self, payload: CreateSketchInput) -> OperationResult:
        if not payload.segments:
            return self._invalid_input("Sketch must contain at least one segment.")

        # Compute bounding box of 2D segments
        xs: list[float] = []
        ys: list[float] = []
        for seg in payload.segments:
            if seg.start:
                xs.append(seg.start[0]); ys.append(seg.start[1])
            if seg.end:
                xs.append(seg.end[0]); ys.append(seg.end[1])
            if seg.center:
                r = seg.radius or 0.0
                xs.extend([seg.center[0] - r, seg.center[0] + r])
                ys.extend([seg.center[1] - r, seg.center[1] + r])

        if not xs:
            return self._invalid_input("Sketch segments have no defined points.")

        ox, oy, oz = payload.origin
        # Map 2D bbox to 3D based on plane
        min2x, max2x = min(xs), max(xs)
        min2y, max2y = min(ys), max(ys)
        if payload.plane == "XZ":
            bbox = BoundingBox(min_x=ox + min2x, min_y=oy, min_z=oz + min2y,
                               max_x=ox + max2x, max_y=oy, max_z=oz + max2y)
        elif payload.plane == "YZ":
            bbox = BoundingBox(min_x=ox, min_y=oy + min2x, min_z=oz + min2y,
                               max_x=ox, max_y=oy + max2x, max_z=oz + max2y)
        else:  # XY
            bbox = BoundingBox(min_x=ox + min2x, min_y=oy + min2y, min_z=oz,
                               max_x=ox + max2x, max_y=oy + max2y, max_z=oz)

        shape = self._make_shape(
            kind="sketch",
            bbox=bbox,
            volume=0.0,
            parameters=payload.model_dump(),
            manifold=False,
            edge_count=len(payload.segments),
            face_count=0,
        )
        return self._success(shape, "create_sketch")

    def extrude(self, payload: ExtrudeInput) -> OperationResult:
        sketch = self.store.get(payload.sketch_id)
        if not sketch:
            return self._shape_not_found(payload.sketch_id)
        if abs(payload.distance) <= self.tolerance:
            return self._invalid_input("Extrude distance must be non-zero.")

        d = abs(payload.distance)
        if payload.both:
            d *= 2
        sb = sketch.bbox
        # Extrude along Z (most common; sketch plane defines this)
        bbox = BoundingBox(
            min_x=sb.min_x, min_y=sb.min_y,
            min_z=sb.min_z - (d / 2 if payload.both else 0.0),
            max_x=sb.max_x, max_y=sb.max_y,
            max_z=sb.max_z + (d / 2 if payload.both else d),
        )
        area_2d = max(self.tolerance, (sb.max_x - sb.min_x) * (sb.max_y - sb.min_y))
        vol = area_2d * d
        shape = self._make_shape(
            kind="extrude",
            bbox=bbox,
            volume=vol,
            parameters=payload.model_dump(),
            edge_count=12,
            face_count=6,
            source_ids=[sketch.id],
        )
        return self._success(shape, "extrude")

    # ── Revolve ─────────────────────────────────────────────────────

    def revolve(self, payload: RevolveInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)
        if abs(payload.angle) <= self.tolerance:
            return self._invalid_input("Revolve angle must be non-zero.")

        # Estimate: revolve the profile's bbox extent around the axis
        sb = shape.bbox
        max_extent = max(
            abs(sb.max_x - payload.axis_origin[0]),
            abs(sb.min_x - payload.axis_origin[0]),
            abs(sb.max_y - payload.axis_origin[1]),
            abs(sb.min_y - payload.axis_origin[1]),
        )
        h = sb.max_z - sb.min_z
        frac = min(abs(payload.angle), 360.0) / 360.0
        vol = math.pi * max_extent ** 2 * max(h, self.tolerance) * frac
        bbox = BoundingBox(
            min_x=-max_extent, min_y=-max_extent, min_z=sb.min_z,
            max_x=max_extent, max_y=max_extent, max_z=sb.max_z,
        )
        shape_out = self._make_shape(
            kind="revolve",
            bbox=bbox,
            volume=vol,
            parameters=payload.model_dump(),
            edge_count=4,
            face_count=4,
            source_ids=[shape.id],
        )
        return self._success(shape_out, "revolve")

    # ── Sweep ───────────────────────────────────────────────────────

    def sweep(self, payload: SweepInput) -> OperationResult:
        profile = self.store.get(payload.profile_id)
        if not profile:
            return self._shape_not_found(payload.profile_id)
        path = self.store.get(payload.path_id)
        if not path:
            return self._shape_not_found(payload.path_id)

        # Union bboxes as approximation
        bbox = union_bbox(profile.bbox, path.bbox)
        vol = max(self.tolerance, profile.volume if profile.volume > 0 else bbox.volume() * 0.1)
        shape_out = self._make_shape(
            kind="sweep",
            bbox=bbox,
            volume=vol,
            parameters=payload.model_dump(),
            edge_count=8,
            face_count=6,
            source_ids=[profile.id, path.id],
        )
        return self._success(shape_out, "sweep")

    # ── Loft ────────────────────────────────────────────────────────

    def loft(self, payload: LoftInput) -> OperationResult:
        profiles: list[ShapeData] = []
        for pid in payload.profile_ids:
            p = self.store.get(pid)
            if not p:
                return self._shape_not_found(pid)
            profiles.append(p)

        # Combine bboxes
        combined_bbox = profiles[0].bbox
        for p in profiles[1:]:
            combined_bbox = union_bbox(combined_bbox, p.bbox)
        vol = max(self.tolerance, combined_bbox.volume() * 0.5)

        shape_out = self._make_shape(
            kind="loft",
            bbox=combined_bbox,
            volume=vol,
            parameters=payload.model_dump(),
            edge_count=max(4, sum(len(p.edge_ids) for p in profiles)),
            face_count=max(2, len(profiles) + 2),
            source_ids=payload.profile_ids,
        )
        return self._success(shape_out, "loft")

    # ── Linear pattern ──────────────────────────────────────────────

    def linear_pattern(self, payload: LinearPatternInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)
        if payload.spacing <= self.tolerance:
            return self._invalid_input("Pattern spacing must be greater than tolerance.")

        d = _vec3_normalise(payload.direction)
        total_offset = payload.spacing * (payload.count - 1)
        bbox = BoundingBox(
            min_x=shape.bbox.min_x + min(0.0, d[0] * total_offset),
            min_y=shape.bbox.min_y + min(0.0, d[1] * total_offset),
            min_z=shape.bbox.min_z + min(0.0, d[2] * total_offset),
            max_x=shape.bbox.max_x + max(0.0, d[0] * total_offset),
            max_y=shape.bbox.max_y + max(0.0, d[1] * total_offset),
            max_z=shape.bbox.max_z + max(0.0, d[2] * total_offset),
        )
        shape_out = self._make_shape(
            kind="linear_pattern",
            bbox=bbox,
            volume=shape.volume * payload.count,
            parameters=payload.model_dump(),
            edge_count=len(shape.edge_ids) * payload.count,
            face_count=len(shape.face_ids) * payload.count,
            source_ids=[shape.id],
        )
        return self._success(shape_out, "linear_pattern")

    # ── Circular pattern ────────────────────────────────────────────

    def circular_pattern(self, payload: CircularPatternInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)

        # Containing bbox: expand to maximum extent from axis
        sb = shape.bbox
        ax = payload.axis_origin
        max_r = max(
            math.sqrt((sb.max_x - ax[0]) ** 2 + (sb.max_y - ax[1]) ** 2),
            math.sqrt((sb.min_x - ax[0]) ** 2 + (sb.min_y - ax[1]) ** 2),
            math.sqrt((sb.max_x - ax[0]) ** 2 + (sb.min_y - ax[1]) ** 2),
            math.sqrt((sb.min_x - ax[0]) ** 2 + (sb.max_y - ax[1]) ** 2),
        )
        bbox = BoundingBox(
            min_x=ax[0] - max_r, min_y=ax[1] - max_r, min_z=sb.min_z,
            max_x=ax[0] + max_r, max_y=ax[1] + max_r, max_z=sb.max_z,
        )
        shape_out = self._make_shape(
            kind="circular_pattern",
            bbox=bbox,
            volume=shape.volume * payload.count,
            parameters=payload.model_dump(),
            edge_count=len(shape.edge_ids) * payload.count,
            face_count=len(shape.face_ids) * payload.count,
            source_ids=[shape.id],
        )
        return self._success(shape_out, "circular_pattern")

    # ── Mirror ──────────────────────────────────────────────────────

    def mirror(self, payload: MirrorInput) -> OperationResult:
        shape = self.store.get(payload.shape_id)
        if not shape:
            return self._shape_not_found(payload.shape_id)

        # Mirror bbox across the plane
        n = _vec3_normalise(payload.plane_normal)
        sb = shape.bbox

        def _reflect(pt: tuple[float, float, float]) -> tuple[float, float, float]:
            ox, oy, oz = payload.plane_origin
            dx, dy, dz = pt[0] - ox, pt[1] - oy, pt[2] - oz
            dot = dx * n[0] + dy * n[1] + dz * n[2]
            return (pt[0] - 2 * dot * n[0], pt[1] - 2 * dot * n[1], pt[2] - 2 * dot * n[2])

        corners = [
            (sb.min_x, sb.min_y, sb.min_z), (sb.max_x, sb.min_y, sb.min_z),
            (sb.min_x, sb.max_y, sb.min_z), (sb.max_x, sb.max_y, sb.min_z),
            (sb.min_x, sb.min_y, sb.max_z), (sb.max_x, sb.min_y, sb.max_z),
            (sb.min_x, sb.max_y, sb.max_z), (sb.max_x, sb.max_y, sb.max_z),
        ]
        mirrored = [_reflect(c) for c in corners]
        all_pts = corners + mirrored
        bbox = BoundingBox(
            min_x=min(p[0] for p in all_pts), min_y=min(p[1] for p in all_pts), min_z=min(p[2] for p in all_pts),
            max_x=max(p[0] for p in all_pts), max_y=max(p[1] for p in all_pts), max_z=max(p[2] for p in all_pts),
        )
        shape_out = self._make_shape(
            kind="mirror",
            bbox=bbox,
            volume=shape.volume * 2,
            parameters=payload.model_dump(),
            edge_count=len(shape.edge_ids) * 2,
            face_count=len(shape.face_ids) * 2,
            source_ids=[shape.id],
        )
        return self._success(shape_out, "mirror")

    # ── Topology ────────────────────────────────────────────────────

    def get_topology(self, shape_id: str) -> TopologyMap:
        """Return a synthetic topology map for *shape_id*."""
        shape = self.store.get(shape_id)
        if shape is None:
            raise ValueError(f"Shape '{shape_id}' not found.")
        return build_synthetic_topology(shape.id, shape.kind, shape.bbox, shape.edge_ids)

# ── Utility ─────────────────────────────────────────────────────────


def _vec3_normalise(v: tuple[float, float, float]) -> tuple[float, float, float]:
    ln = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if ln < 1e-12:
        return (0.0, 0.0, 1.0)
    return (v[0] / ln, v[1] / ln, v[2] / ln)
