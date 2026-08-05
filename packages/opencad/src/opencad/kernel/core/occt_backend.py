"""OCCT geometry backend powered by CadQuery / OCP.

Implements :class:`KernelBackend` with real B-rep geometry via
OpenCASCADE Technology. Install with ``uv sync --extra occt``.

"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import math
from pathlib import Path
from typing import Any, Literal

HAS_OCCT = (
    importlib.util.find_spec("cadquery") is not None
    and importlib.util.find_spec("OCP") is not None
)

# ── Dynamically-loaded OCCT symbols ────────────────────────────────

cq = None

# BRep / topology
BRep_Tool = None
BRepAlgoAPI_Cut = None
BRepAlgoAPI_Fuse = None
BRepAlgoAPI_Common = None
BRepBndLib = None
BRepCheck_Analyzer = None
BRepFilletAPI_MakeFillet = None
BRepFilletAPI_MakeChamfer = None
BRepGProp = None
BRepMesh_IncrementalMesh = None
BRepOffsetAPI_MakeOffsetShape = None
BRepOffsetAPI_MakeThickSolid = None
BRepPrimAPI_MakeRevol = None
BRepOffsetAPI_MakePipe = None
BRepOffsetAPI_ThruSections = None
BRepBuilderAPI_Transform = None
BRepBuilderAPI_MakeWire = None
BRepBuilderAPI_MakeEdge = None
BRepBuilderAPI_MakeFace = None
BRepAdaptor_Surface = None

# Primitives
BRepPrimAPI_MakeCone = None
BRepPrimAPI_MakeTorus = None

# Geometry primitives
gp_Pnt = None
gp_Dir = None
gp_Ax1 = None
gp_Ax2 = None
gp_Trsf = None
gp_Vec = None
gp_Circ = None
GC_MakeArcOfCircle = None

# Bounding box / properties
Bnd_Box = None
GProp_GProps = None

# Topology constants / explorers
TopAbs_EDGE = None
TopAbs_FACE = None
TopAbs_WIRE = None
TopAbs_REVERSED = None
TopExp = None
TopExp_Explorer = None
TopLoc_Location = None
TopoDS = None
TopoDS_Shape = Any
StlAPI_Reader = None

# Lists / maps
TopTools_ListOfShape = None
TopTools_IndexedMapOfShape = None

if HAS_OCCT:  # pragma: no branch
    cq = importlib.import_module("cadquery")

    BRep_Tool = importlib.import_module("OCP.BRep").BRep_Tool

    algo_mod = importlib.import_module("OCP.BRepAlgoAPI")
    BRepAlgoAPI_Cut = algo_mod.BRepAlgoAPI_Cut
    BRepAlgoAPI_Fuse = algo_mod.BRepAlgoAPI_Fuse
    BRepAlgoAPI_Common = algo_mod.BRepAlgoAPI_Common

    BRepBndLib = importlib.import_module("OCP.BRepBndLib").BRepBndLib
    BRepCheck_Analyzer = importlib.import_module("OCP.BRepCheck").BRepCheck_Analyzer

    fillet_mod = importlib.import_module("OCP.BRepFilletAPI")
    BRepFilletAPI_MakeFillet = fillet_mod.BRepFilletAPI_MakeFillet
    BRepFilletAPI_MakeChamfer = fillet_mod.BRepFilletAPI_MakeChamfer

    BRepGProp = importlib.import_module("OCP.BRepGProp").BRepGProp
    BRepMesh_IncrementalMesh = importlib.import_module("OCP.BRepMesh").BRepMesh_IncrementalMesh

    offset_mod = importlib.import_module("OCP.BRepOffsetAPI")
    BRepOffsetAPI_MakeOffsetShape = offset_mod.BRepOffsetAPI_MakeOffsetShape
    BRepOffsetAPI_MakeThickSolid = offset_mod.BRepOffsetAPI_MakeThickSolid
    BRepOffsetAPI_MakePipe = offset_mod.BRepOffsetAPI_MakePipe
    BRepOffsetAPI_ThruSections = offset_mod.BRepOffsetAPI_ThruSections

    prim_mod = importlib.import_module("OCP.BRepPrimAPI")
    BRepPrimAPI_MakeRevol = prim_mod.BRepPrimAPI_MakeRevol
    BRepPrimAPI_MakeCone = prim_mod.BRepPrimAPI_MakeCone
    BRepPrimAPI_MakeTorus = prim_mod.BRepPrimAPI_MakeTorus

    builder_mod = importlib.import_module("OCP.BRepBuilderAPI")
    BRepBuilderAPI_Transform = builder_mod.BRepBuilderAPI_Transform
    BRepBuilderAPI_MakeWire = builder_mod.BRepBuilderAPI_MakeWire
    BRepBuilderAPI_MakeEdge = builder_mod.BRepBuilderAPI_MakeEdge
    BRepBuilderAPI_MakeFace = builder_mod.BRepBuilderAPI_MakeFace

    BRepAdaptor_Surface = importlib.import_module("OCP.BRepAdaptor").BRepAdaptor_Surface

    gp_mod = importlib.import_module("OCP.gp")
    gp_Pnt = gp_mod.gp_Pnt
    gp_Dir = gp_mod.gp_Dir
    gp_Ax1 = gp_mod.gp_Ax1
    gp_Ax2 = gp_mod.gp_Ax2
    gp_Trsf = gp_mod.gp_Trsf
    gp_Vec = gp_mod.gp_Vec
    gp_Circ = gp_mod.gp_Circ

    GC_MakeArcOfCircle = importlib.import_module("OCP.GC").GC_MakeArcOfCircle

    Bnd_Box = importlib.import_module("OCP.Bnd").Bnd_Box
    GProp_GProps = importlib.import_module("OCP.GProp").GProp_GProps

    topabs_mod = importlib.import_module("OCP.TopAbs")
    TopAbs_EDGE = topabs_mod.TopAbs_EDGE
    TopAbs_FACE = topabs_mod.TopAbs_FACE
    TopAbs_WIRE = topabs_mod.TopAbs_WIRE
    TopAbs_REVERSED = topabs_mod.TopAbs_REVERSED

    topexp_mod = importlib.import_module("OCP.TopExp")
    TopExp = topexp_mod.TopExp
    TopExp_Explorer = topexp_mod.TopExp_Explorer
    TopLoc_Location = importlib.import_module("OCP.TopLoc").TopLoc_Location

    topods_mod = importlib.import_module("OCP.TopoDS")
    TopoDS = topods_mod.TopoDS
    TopoDS_Shape = topods_mod.TopoDS_Shape

    StlAPI_Reader = importlib.import_module("OCP.StlAPI").StlAPI_Reader

    toptools_mod = importlib.import_module("OCP.TopTools")
    TopTools_ListOfShape = toptools_mod.TopTools_ListOfShape
    TopTools_IndexedMapOfShape = toptools_mod.TopTools_IndexedMapOfShape

from opencad.kernel.core.checks import check_bbox_overlap, check_manifold, check_nonzero_volume
from opencad.kernel.core.errors import ErrorCode, make_failure
from opencad.kernel.core.models import (
    BoundingBox,
    MeshData,
    MeshFaceGroup,
    OperationResult,
    ShapeData,
    SubshapeKind,
    SubshapeRef,
    Success,
    TopologyMap,
)
from opencad.kernel.core.store import IdStrategy, ShapeStore
from opencad.kernel.core.topology import _auto_tags_for_normal
from opencad.kernel.operations.schemas import (
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
    SketchSegment,
    SweepInput,
)

logger = logging.getLogger(__name__)

BooleanOp = Literal["boolean_union", "boolean_cut", "boolean_intersection"]


def _require_occt() -> None:
    if not HAS_OCCT:
        raise RuntimeError(
            "CadQuery / OCP is required for the OCCT backend.  "
            "Install with: uv sync --extra occt"
        )


# ── Geometry helpers ────────────────────────────────────────────────


def _bbox_from_shape(shape: Any) -> BoundingBox:
    """Compute axis-aligned bounding box via OCCT Bnd_Box."""
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return BoundingBox(
        min_x=xmin, min_y=ymin, min_z=zmin,
        max_x=xmax, max_y=ymax, max_z=zmax,
    )


def _volume_from_shape(shape: Any) -> float:
    """Compute solid volume via GProp_GProps."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return abs(props.Mass())


def _is_manifold(shape: Any) -> bool:
    """Run BRepCheck_Analyzer to test validity."""
    analyzer = BRepCheck_Analyzer(shape)
    return analyzer.IsValid()


def _edges_from_shape(shape: Any) -> list[Any]:
    """Return each edge once, in stable first-encountered order.

    An edge is shared by the faces that meet along it, and TopExp_Explorer
    yields it once per face, so walking it directly reports a box's 12 edges
    24 times. MapShapes indexes on shape identity, which collapses those
    repeats while keeping traversal order.
    """
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
    return [TopoDS.Edge_s(edge_map.FindKey(i)) for i in range(1, edge_map.Extent() + 1)]


def _edge_list(shape: Any, shape_id: str) -> list[str]:
    """Enumerate edges and return deterministic IDs."""
    return [f"{shape_id}:edge:{idx}" for idx in range(len(_edges_from_shape(shape)))]


def _edge_by_index(shape: Any, index: int) -> Any:
    """Return the TopoDS_Edge at *index* for fillet operations."""
    edges = _edges_from_shape(shape)
    if not 0 <= index < len(edges):
        raise IndexError(f"Edge index {index} out of range (shape has {len(edges)} edges)")
    return edges[index]


def _face_list(shape: Any, shape_id: str) -> list[str]:
    """Enumerate faces and return deterministic IDs."""
    ids: list[str] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    idx = 0
    while explorer.More():
        ids.append(f"{shape_id}:face:{idx}")
        idx += 1
        explorer.Next()
    return ids


def _face_by_index(shape: Any, index: int) -> Any:
    """Return the TopoDS_Face at *index*."""
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    i = 0
    while explorer.More():
        if i == index:
            return TopoDS.Face_s(explorer.Current())
        i += 1
        explorer.Next()
    raise IndexError(f"Face index {index} out of range (shape has {i} faces)")


def _wire_by_index(shape: Any, index: int) -> Any:
    """Return the TopoDS_Wire at *index*."""
    explorer = TopExp_Explorer(shape, TopAbs_WIRE)
    i = 0
    while explorer.More():
        if i == index:
            return TopoDS.Wire_s(explorer.Current())
        i += 1
        explorer.Next()
    raise IndexError(f"Wire index {index} out of range (shape has {i} wires)")


def _sketch_edge(
    segment: SketchSegment,
    *,
    plane: str,
    origin: tuple[float, float, float],
) -> Any | None:
    """Build one OCCT edge without deciding how profile loops are combined."""
    ox, oy, oz = origin

    def point(coordinates: tuple[float, float]) -> Any:
        first, second = coordinates
        if plane == "XZ":
            return gp_Pnt(ox + first, oy, oz + second)
        if plane == "YZ":
            return gp_Pnt(ox, oy + first, oz + second)
        return gp_Pnt(ox + first, oy + second, oz)

    if segment.type == "line" and segment.start and segment.end:
        return BRepBuilderAPI_MakeEdge(point(segment.start), point(segment.end)).Edge()

    if segment.type == "circle" and segment.center and segment.radius:
        cx, cy = segment.center
        if plane == "XZ":
            axis = gp_Ax2(gp_Pnt(ox + cx, oy, oz + cy), gp_Dir(0, 1, 0))
        elif plane == "YZ":
            axis = gp_Ax2(gp_Pnt(ox, oy + cx, oz + cy), gp_Dir(1, 0, 0))
        else:
            axis = gp_Ax2(gp_Pnt(ox + cx, oy + cy, oz), gp_Dir(0, 0, 1))
        return BRepBuilderAPI_MakeEdge(gp_Circ(axis, segment.radius)).Edge()

    if (
        segment.type == "arc"
        and segment.start
        and segment.end
        and segment.center
        and segment.radius
    ):
        cx, cy = segment.center
        midpoint = point((cx, cy + segment.radius))
        arc = GC_MakeArcOfCircle(point(segment.start), midpoint, point(segment.end)).Value()
        return BRepBuilderAPI_MakeEdge(arc).Edge()

    return None


# ── Topology reference helpers ──────────────────────────────────────


def _face_centroid(face: Any) -> tuple[float, float, float]:
    """Compute centroid of a topological face via surface properties."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    c = props.CentreOfMass()
    return (c.X(), c.Y(), c.Z())


def _face_normal_at_centroid(face: Any) -> tuple[float, float, float] | None:
    """Evaluate the outward face normal at its centroid."""
    try:
        surf = BRepAdaptor_Surface(face)
        u = (surf.FirstUParameter() + surf.LastUParameter()) / 2.0
        v = (surf.FirstVParameter() + surf.LastVParameter()) / 2.0
        pnt = surf.Value(u, v)
        # Compute normal via cross of tangent vectors
        d1u, d1v = surf.D1(u, v, gp_Pnt(), gp_Vec(), gp_Vec())  # type: ignore[call-arg]
        # Fallback: use generic normal API
    except Exception:
        pass

    # Robust fallback: get normal from BRep_Tool
    try:
        surf = BRepAdaptor_Surface(face)
        u = (surf.FirstUParameter() + surf.LastUParameter()) / 2.0
        v = (surf.FirstVParameter() + surf.LastVParameter()) / 2.0
        gp_pnt = gp_Pnt()
        normal_vec = gp_Vec()
        # Use the ShapeAnalysis approach
        from OCP.BRepGProp import BRepGProp_Face as _GPFace  # type: ignore[import]
        gpf = _GPFace(face)
        pt = gp_Pnt()
        nv = gp_Vec()
        gpf.Normal(u, v, pt, nv)
        ln = nv.Magnitude()
        if ln > 1e-12:
            return (nv.X() / ln, nv.Y() / ln, nv.Z() / ln)
    except Exception:
        pass
    return None


def _face_area(face: Any) -> float:
    """Compute surface area of a face."""
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    return abs(props.Mass())


def _edge_centroid(edge: Any) -> tuple[float, float, float]:
    """Compute centroid of an edge via linear properties."""
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, props)
    c = props.CentreOfMass()
    return (c.X(), c.Y(), c.Z())


def _edge_length(edge: Any) -> float:
    """Compute length of an edge."""
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, props)
    return abs(props.Mass())


def _build_topology_map(shape: Any, shape_id: str) -> TopologyMap:
    """Build a full TopologyMap from a native OCCT shape."""
    face_refs: list[SubshapeRef] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    idx = 0
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        centroid = _face_centroid(face)
        normal = _face_normal_at_centroid(face)
        area = _face_area(face)
        tags = _auto_tags_for_normal(normal)
        face_refs.append(SubshapeRef(
            id=f"{shape_id}:face:{idx}",
            kind=SubshapeKind.FACE,
            index=idx,
            centroid=centroid,
            normal=normal,
            area=area,
            tags=tags,
        ))
        idx += 1
        explorer.Next()

    edge_refs: list[SubshapeRef] = []
    for idx, edge in enumerate(_edges_from_shape(shape)):
        centroid = _edge_centroid(edge)
        length = _edge_length(edge)
        edge_refs.append(SubshapeRef(
            id=f"{shape_id}:edge:{idx}",
            kind=SubshapeKind.EDGE,
            index=idx,
            centroid=centroid,
            length=length,
            tags=[],
        ))

    return TopologyMap(shape_id=shape_id, faces=face_refs, edges=edge_refs)


def _faces_from_shape(shape: Any) -> list[Any]:
    """Return faces in the same stable explorer order used by tessellation."""
    result: list[Any] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        result.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return result


def _tessellate_shape(
    shape: Any,
    deflection: float = 0.1,
    face_owners: list[str] | None = None,
    default_owner_shape_id: str = "",
) -> MeshData:
    """Tessellate a TopoDS_Shape and return MeshData (vertices, faces, normals)."""
    BRepMesh_IncrementalMesh(shape, deflection)

    vertices: list[float] = []
    normals: list[float] = []
    faces: list[int] = []
    face_groups: list[MeshFaceGroup] = []
    vertex_offset = 0
    face_index = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)

        if triangulation is None:
            face_index += 1
            explorer.Next()
            continue

        trsf = location.Transformation()
        nb_nodes = triangulation.NbNodes()
        nb_tris = triangulation.NbTriangles()

        # Vertices
        for i in range(1, nb_nodes + 1):
            node = triangulation.Node(i).Transformed(trsf)
            vertices.extend([node.X(), node.Y(), node.Z()])

        # Normals — compute from face surface if available, else zero
        if triangulation.HasNormals():
            for i in range(1, nb_nodes + 1):
                n = triangulation.Normal(i)
                normals.extend([n.X(), n.Y(), n.Z()])
        else:
            normals.extend([0.0, 0.0, 0.0] * nb_nodes)

        # Triangles — reverse winding for REVERSED faces so normals point outward
        reversed_face = face.Orientation() == TopAbs_REVERSED
        group_start = len(faces)
        for i in range(1, nb_tris + 1):
            tri = triangulation.Triangle(i)
            n1, n2, n3 = tri.Get()
            if reversed_face:
                faces.extend([
                    n1 - 1 + vertex_offset,
                    n3 - 1 + vertex_offset,
                    n2 - 1 + vertex_offset,
                ])
            else:
                faces.extend([
                    n1 - 1 + vertex_offset,
                    n2 - 1 + vertex_offset,
                    n3 - 1 + vertex_offset,
                ])

        owner_shape_id = (
            face_owners[face_index]
            if face_owners is not None and face_index < len(face_owners)
            else default_owner_shape_id
        )
        face_groups.append(MeshFaceGroup(
            start=group_start,
            count=len(faces) - group_start,
            face_index=face_index,
            owner_shape_id=owner_shape_id,
        ))
        vertex_offset += nb_nodes
        face_index += 1
        explorer.Next()

    return MeshData(vertices=vertices, faces=faces, normals=normals, face_groups=face_groups)


def _tessellate_face(
    shape: Any,
    face_index: int,
    deflection: float = 0.1,
    owner_shape_id: str = "",
) -> tuple[MeshData, int]:
    """Tessellate a single face from the shape.

    Returns ``(MeshData, total_face_count)`` for streaming use.
    """
    BRepMesh_IncrementalMesh(shape, deflection)

    total_faces = 0
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    current_index = 0
    mesh = MeshData()

    while explorer.More():
        total_faces += 1
        if current_index == face_index:
            face = TopoDS.Face_s(explorer.Current())
            location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation_s(face, location)

            if triangulation is not None:
                trsf = location.Transformation()
                nb_nodes = triangulation.NbNodes()
                nb_tris = triangulation.NbTriangles()

                verts: list[float] = []
                norms: list[float] = []
                tris: list[int] = []

                for i in range(1, nb_nodes + 1):
                    node = triangulation.Node(i).Transformed(trsf)
                    verts.extend([node.X(), node.Y(), node.Z()])

                if triangulation.HasNormals():
                    for i in range(1, nb_nodes + 1):
                        n = triangulation.Normal(i)
                        norms.extend([n.X(), n.Y(), n.Z()])
                else:
                    norms.extend([0.0, 0.0, 0.0] * nb_nodes)

                reversed_face = face.Orientation() == TopAbs_REVERSED
                for i in range(1, nb_tris + 1):
                    tri = triangulation.Triangle(i)
                    n1, n2, n3 = tri.Get()
                    if reversed_face:
                        tris.extend([n1 - 1, n3 - 1, n2 - 1])
                    else:
                        tris.extend([n1 - 1, n2 - 1, n3 - 1])

                mesh = MeshData(
                    vertices=verts,
                    faces=tris,
                    normals=norms,
                    face_groups=[MeshFaceGroup(
                        start=0,
                        count=len(tris),
                        face_index=face_index,
                        owner_shape_id=owner_shape_id,
                    )],
                )

        current_index += 1
        explorer.Next()

    # Need a second pass to count remaining faces if we broke early
    while explorer.More():
        total_faces += 1
        explorer.Next()

    return mesh, total_faces


def _count_faces(shape: Any) -> int:
    """Count the number of topological faces on a shape."""
    count = 0
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        count += 1
        explorer.Next()
    return count


# ── Backend implementation ──────────────────────────────────────────


class OcctBackend:
    """OCCT-backed geometry engine implementing :class:`KernelBackend`."""

    def __init__(
        self,
        tolerance: float = 1e-6,
        id_strategy: IdStrategy = "uuid",
    ) -> None:
        _require_occt()
        self.tolerance = tolerance
        self._store = ShapeStore(id_strategy=id_strategy)
        self._native: dict[str, Any] = {}
        self._face_owners: dict[str, list[str]] = {}

    @property
    def store(self) -> ShapeStore:
        return self._store

    # ── internal helpers ────────────────────────────────────────────

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

    def _register_shape(
        self,
        kind: str,
        native: Any,
        parameters: dict[str, Any],
        source_ids: list[str] | None = None,
    ) -> ShapeData:
        shape_id = self._store.new_id(kind)
        bbox = _bbox_from_shape(native)
        volume = _volume_from_shape(native)
        manifold = _is_manifold(native)
        edge_ids = _edge_list(native, shape_id)
        face_ids = _face_list(native, shape_id)

        shape = ShapeData(
            id=shape_id,
            kind=kind,
            parameters=parameters,
            bbox=bbox,
            volume=volume,
            manifold=manifold,
            edge_ids=edge_ids,
            face_ids=face_ids,
            source_ids=source_ids or [],
        )
        self._store.add(shape)
        self._native[shape_id] = native
        self._face_owners[shape_id] = [shape_id] * len(face_ids)
        return shape

    def _inherit_modified_face_owners(
        self,
        result_shape_id: str,
        source_shape_ids: list[str],
        builder: Any,
    ) -> None:
        """Propagate owners for preserved/modified faces using OCCT history.

        Faces generated by the current operation deliberately retain the
        result shape as owner. That makes fillet/chamfer and boolean-created
        faces selectable as contributions of the operation itself.
        """
        result_native = self._get_native(result_shape_id)
        if result_native is None:
            return

        result_faces = _faces_from_shape(result_native)
        owners = [result_shape_id] * len(result_faces)

        for source_shape_id in source_shape_ids:
            source_native = self._get_native(source_shape_id)
            if source_native is None:
                continue
            source_faces = _faces_from_shape(source_native)
            source_owners = self._face_owners.get(
                source_shape_id,
                [source_shape_id] * len(source_faces),
            )

            for source_index, source_face in enumerate(source_faces):
                candidates = [source_face]
                try:
                    candidates.extend(list(builder.Modified(source_face)))
                except (AttributeError, RuntimeError):
                    pass

                inherited_owner = (
                    source_owners[source_index]
                    if source_index < len(source_owners)
                    else source_shape_id
                )
                for candidate in candidates:
                    for result_index, result_face in enumerate(result_faces):
                        if owners[result_index] == result_shape_id and result_face.IsSame(candidate):
                            owners[result_index] = inherited_owner

        self._face_owners[result_shape_id] = owners

    def _success(self, shape: ShapeData, operation: str, **metadata: object) -> Success:
        return Success(shape_id=shape.id, shape=shape, metadata={"operation": operation, **metadata})

    def _get_native(self, shape_id: str) -> Any | None:
        return self._native.get(shape_id)

    # ── Primitives ──────────────────────────────────────────────────

    def create_box(self, payload: CreateBoxInput) -> OperationResult:
        if payload.length <= self.tolerance or payload.width <= self.tolerance or payload.height <= self.tolerance:
            return self._invalid_input("Box dimensions must be greater than tolerance.")

        wp = cq.Workplane("XY").box(payload.length, payload.width, payload.height, centered=False)
        native = wp.val().wrapped
        shape = self._register_shape("box", native, payload.model_dump())
        return self._success(shape, "create_box")

    def create_cylinder(self, payload: CreateCylinderInput) -> OperationResult:
        if payload.radius <= self.tolerance or payload.height <= self.tolerance:
            return self._invalid_input("Cylinder radius and height must be greater than tolerance.")

        wp = cq.Workplane("XY").cylinder(payload.height, payload.radius)
        native = wp.val().wrapped
        shape = self._register_shape("cylinder", native, payload.model_dump())
        return self._success(shape, "create_cylinder")

    def create_sphere(self, payload: CreateSphereInput) -> OperationResult:
        if payload.radius <= self.tolerance:
            return self._invalid_input("Sphere radius must be greater than tolerance.")

        wp = cq.Workplane("XY").sphere(payload.radius)
        native = wp.val().wrapped
        shape = self._register_shape("sphere", native, payload.model_dump())
        return self._success(shape, "create_sphere")

    # ── Booleans ────────────────────────────────────────────────────

    def _fetch_pair(self, payload: BooleanInput) -> tuple[ShapeData, ShapeData] | OperationResult:
        a = self._store.get(payload.shape_a_id)
        if not a:
            return self._shape_not_found(payload.shape_a_id)
        b = self._store.get(payload.shape_b_id)
        if not b:
            return self._shape_not_found(payload.shape_b_id)
        return a, b

    def _preflight(self, op: BooleanOp, a: ShapeData, b: ShapeData) -> OperationResult | None:
        for shape in (a, b):
            v = check_nonzero_volume(shape, self.tolerance)
            if v:
                return v
            m = check_manifold(shape)
            if m:
                return m
        if op in {"boolean_union", "boolean_intersection"}:
            overlap = check_bbox_overlap(a, b, self.tolerance)
            if overlap:
                return overlap
        return None

    def _run_boolean(self, op: BooleanOp, payload: BooleanInput) -> OperationResult:
        pair = self._fetch_pair(payload)
        if not isinstance(pair, tuple):
            return pair

        shape_a, shape_b = pair
        preflight = self._preflight(op, shape_a, shape_b)
        if preflight is not None:
            return preflight

        native_a = self._get_native(shape_a.id)
        native_b = self._get_native(shape_b.id)
        if native_a is None or native_b is None:
            return make_failure(
                code=ErrorCode.BOOLEAN_KERNEL_ERROR,
                message="Native OCCT shape not found for boolean operand.",
                suggestion="Recreate the input shapes.",
                failed_check="native_lookup",
            )

        try:
            if op == "boolean_union":
                algo = BRepAlgoAPI_Fuse(native_a, native_b)
            elif op == "boolean_cut":
                algo = BRepAlgoAPI_Cut(native_a, native_b)
            else:
                algo = BRepAlgoAPI_Common(native_a, native_b)

            if not algo.IsDone():
                return make_failure(
                    code=ErrorCode.BOOLEAN_KERNEL_ERROR,
                    message=f"OCCT {op} did not converge.",
                    suggestion="Inspect input geometry and retry with cleaned shapes.",
                    failed_check="kernel_execution",
                )

            result_native = algo.Shape()
            result_volume = _volume_from_shape(result_native)

            if result_volume <= self.tolerance:
                return make_failure(
                    code=ErrorCode.ZERO_VOLUME,
                    message=f"Boolean {op} produced zero-volume result.",
                    suggestion="Adjust shape overlap or choose a different operation.",
                    failed_check="boolean_result_volume",
                )

            shape = self._register_shape(
                op,
                result_native,
                {"shape_a_id": shape_a.id, "shape_b_id": shape_b.id},
                source_ids=[shape_a.id, shape_b.id],
            )
            self._inherit_modified_face_owners(shape.id, [shape_a.id, shape_b.id], algo)
            return self._success(shape, op, preflight="passed")

        except Exception as exc:
            return make_failure(
                code=ErrorCode.BOOLEAN_KERNEL_ERROR,
                message=f"Boolean operation failed: {exc}",
                suggestion="Inspect input geometry and retry with cleaned shapes.",
                failed_check="kernel_execution",
            )

    def boolean_union(self, payload: BooleanInput) -> OperationResult:
        return self._run_boolean("boolean_union", payload)

    def boolean_cut(self, payload: BooleanInput) -> OperationResult:
        return self._run_boolean("boolean_cut", payload)

    def boolean_intersection(self, payload: BooleanInput) -> OperationResult:
        return self._run_boolean("boolean_intersection", payload)

    # ── Local operations ────────────────────────────────────────────

    def fillet_edges(self, payload: FilletEdgesInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)

        if not payload.edge_ids:
            return self._invalid_input("At least one edge_id is required for fillet.")
        if payload.radius <= self.tolerance:
            return self._invalid_input("Fillet radius must be greater than tolerance.")

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            fillet = BRepFilletAPI_MakeFillet(native)
            for eid in payload.edge_ids:
                # edge id format: "{shape_id}:edge:{index}"
                parts = eid.split(":edge:")
                if len(parts) != 2 or not parts[1].isdigit():
                    return self._invalid_input(f"Invalid edge ID format: '{eid}'")
                idx = int(parts[1])
                edge = _edge_by_index(native, idx)
                fillet.Add(payload.radius, edge)

            fillet.Build()
            if not fillet.IsDone():
                return make_failure(
                    code=ErrorCode.FILLET_RADIUS_TOO_LARGE,
                    message="Fillet operation did not converge — radius may be too large.",
                    suggestion="Reduce fillet radius or increase base feature size.",
                    failed_check="fillet_build",
                )

            result_native = fillet.Shape()
            shape = self._register_shape(
                "fillet",
                result_native,
                {"shape_id": payload.shape_id, "edge_ids": payload.edge_ids, "radius": payload.radius},
                source_ids=[meta.id],
            )
            self._inherit_modified_face_owners(shape.id, [meta.id], fillet)
            return self._success(shape, "fillet_edges")

        except IndexError:
            return make_failure(
                code=ErrorCode.FILLET_RADIUS_TOO_LARGE,
                message="One or more edge IDs are out of range.",
                suggestion="Use edge IDs from the source shape's edge_ids list.",
                failed_check="edge_lookup",
            )
        except Exception as exc:
            return make_failure(
                code=ErrorCode.FILLET_RADIUS_TOO_LARGE,
                message=f"Fillet failed: {exc}",
                suggestion="Reduce fillet radius or increase base feature size.",
                failed_check="fillet_build",
            )

    def offset_shape(self, payload: OffsetShapeInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            offset = BRepOffsetAPI_MakeOffsetShape()
            offset.PerformByJoin(native, payload.distance, self.tolerance)

            if not offset.IsDone():
                return make_failure(
                    code=ErrorCode.OFFSET_COLLAPSE,
                    message="Offset operation did not converge.",
                    suggestion="Use a smaller offset distance.",
                    failed_check="offset_build",
                )

            result_native = offset.Shape()
            result_volume = _volume_from_shape(result_native)

            if result_volume <= self.tolerance:
                return make_failure(
                    code=ErrorCode.OFFSET_COLLAPSE,
                    message="Offset collapsed the shape to zero volume.",
                    suggestion="Use a smaller negative offset or a positive offset.",
                    failed_check="offset_validity",
                )

            shape = self._register_shape(
                "offset",
                result_native,
                {"shape_id": payload.shape_id, "distance": payload.distance},
                source_ids=[meta.id],
            )
            return self._success(shape, "offset_shape")

        except Exception as exc:
            return make_failure(
                code=ErrorCode.OFFSET_COLLAPSE,
                message=f"Offset failed: {exc}",
                suggestion="Use a smaller offset distance.",
                failed_check="offset_build",
            )

    # ── STEP I/O ────────────────────────────────────────────────────

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
            wp = cq.importers.importStep(str(filepath))
            native = wp.val().wrapped
        except Exception as exc:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message=f"Failed to read STEP file: {exc}",
                suggestion="Verify file path and read permissions.",
                failed_check="step_io",
            )

        shape = self._register_shape("imported_step", native, {"filepath": payload.filepath})
        return self._success(shape, "import_step", imported_from=payload.filepath)

    def export_step(self, payload: ExportStepInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            wp = cq.Workplane("XY").newObject([cq.Shape(native)])
            cq.exporters.export(
                wp,
                str(payload.filepath),
                exportType=cq.exporters.ExportTypes.STEP,
            )
        except Exception as exc:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message=f"Failed to write STEP file: {exc}",
                suggestion="Verify destination directory permissions.",
                failed_check="step_io",
            )

        return Success(
            shape_id=meta.id,
            shape=None,
            metadata={"operation": "export_step", "filepath": payload.filepath},
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
            native = TopoDS_Shape()
            if not StlAPI_Reader().Read(native, str(filepath)) or native.IsNull():
                raise ValueError("OCCT could not read any shape data.")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message=f"Failed to read STL file: {exc}",
                suggestion="Verify that the file is a valid ASCII or binary STL.",
                failed_check="stl_io",
            )
        shape = self._register_shape("imported_stl", native, {"filepath": payload.filepath})
        return self._success(shape, "import_stl", imported_from=payload.filepath)

    def export_stl(self, payload: ExportStlInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)
        filepath = Path(payload.filepath)
        if filepath.suffix.lower() != ".stl":
            return make_failure(
                code=ErrorCode.UNSUPPORTED_FILE_FORMAT,
                message="STL export requires a .stl destination.",
                suggestion="Use a filename ending in .stl.",
                failed_check="stl_extension",
            )
        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)
        try:
            cq.exporters.export(cq.Shape(native), str(filepath), exportType=cq.exporters.ExportTypes.STL)
        except Exception as exc:
            return make_failure(
                code=ErrorCode.IO_ERROR,
                message=f"Failed to write STL file: {exc}",
                suggestion="Verify destination directory permissions.",
                failed_check="stl_io",
            )
        return Success(
            shape_id=meta.id,
            shape=None,
            metadata={"operation": "export_stl", "filepath": payload.filepath},
        )

    # ── Tessellation ────────────────────────────────────────────────

    def tessellate(self, shape_id: str, deflection: float = 0.1) -> MeshData:
        native = self._get_native(shape_id)
        if native is None:
            raise ValueError(f"Shape '{shape_id}' not found for tessellation.")
        return _tessellate_shape(
            native,
            deflection,
            self._face_owners.get(shape_id),
            shape_id,
        )

    def tessellate_face(self, shape_id: str, face_index: int, deflection: float = 0.1) -> tuple[MeshData, int]:
        """Tessellate a single face — used for SSE streaming."""
        native = self._get_native(shape_id)
        if native is None:
            raise ValueError(f"Shape '{shape_id}' not found for tessellation.")
        owners = self._face_owners.get(shape_id, [])
        owner_shape_id = owners[face_index] if face_index < len(owners) else shape_id
        return _tessellate_face(native, face_index, deflection, owner_shape_id)

    def count_faces(self, shape_id: str) -> int:
        native = self._get_native(shape_id)
        if native is None:
            raise ValueError(f"Shape '{shape_id}' not found.")
        return _count_faces(native)

    # ── Escape hatch ────────────────────────────────────────────────

    def get_native_shape(self, shape_id: str) -> Any:
        return self._native.get(shape_id)

    # ── Additional primitives ───────────────────────────────────────

    def create_cone(self, payload: CreateConeInput) -> OperationResult:
        if payload.height <= self.tolerance:
            return self._invalid_input("Cone height must be greater than tolerance.")
        if payload.radius1 <= self.tolerance and payload.radius2 <= self.tolerance:
            return self._invalid_input("At least one cone radius must be > tolerance.")

        try:
            ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
            native = BRepPrimAPI_MakeCone(ax, payload.radius1, payload.radius2, payload.height).Shape()
            shape = self._register_shape("cone", native, payload.model_dump())
            return self._success(shape, "create_cone")
        except Exception as exc:
            return self._invalid_input(f"Cone creation failed: {exc}")

    def create_torus(self, payload: CreateTorusInput) -> OperationResult:
        if payload.major_radius <= self.tolerance or payload.minor_radius <= self.tolerance:
            return self._invalid_input("Torus radii must be > tolerance.")
        if payload.minor_radius >= payload.major_radius:
            return self._invalid_input("Minor radius must be < major radius.")

        try:
            ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1))
            native = BRepPrimAPI_MakeTorus(ax, payload.major_radius, payload.minor_radius).Shape()
            shape = self._register_shape("torus", native, payload.model_dump())
            return self._success(shape, "create_torus")
        except Exception as exc:
            return self._invalid_input(f"Torus creation failed: {exc}")

    # ── Chamfer ─────────────────────────────────────────────────────

    def chamfer_edges(self, payload: ChamferEdgesInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)
        if not payload.edge_ids:
            return self._invalid_input("At least one edge_id is required for chamfer.")
        if payload.distance <= self.tolerance:
            return self._invalid_input("Chamfer distance must be > tolerance.")

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            chamfer = BRepFilletAPI_MakeChamfer(native)
            for eid in payload.edge_ids:
                parts = eid.split(":edge:")
                if len(parts) != 2 or not parts[1].isdigit():
                    return self._invalid_input(f"Invalid edge ID format: '{eid}'")
                idx = int(parts[1])
                edge = _edge_by_index(native, idx)
                chamfer.Add(payload.distance, edge)

            chamfer.Build()
            if not chamfer.IsDone():
                return make_failure(
                    code=ErrorCode.CHAMFER_FAILURE,
                    message="Chamfer did not converge — distance may be too large.",
                    suggestion="Reduce chamfer distance.",
                    failed_check="chamfer_build",
                )

            result_native = chamfer.Shape()
            shape = self._register_shape(
                "chamfer", result_native,
                {"shape_id": payload.shape_id, "edge_ids": payload.edge_ids, "distance": payload.distance},
                source_ids=[meta.id],
            )
            self._inherit_modified_face_owners(shape.id, [meta.id], chamfer)
            return self._success(shape, "chamfer_edges")
        except IndexError:
            return make_failure(
                code=ErrorCode.CHAMFER_FAILURE,
                message="Edge ID out of range.",
                suggestion="Use edge IDs from the source shape's edge_ids list.",
                failed_check="edge_lookup",
            )
        except Exception as exc:
            return make_failure(
                code=ErrorCode.CHAMFER_FAILURE,
                message=f"Chamfer failed: {exc}",
                suggestion="Reduce chamfer distance.",
                failed_check="chamfer_build",
            )

    # ── Shell ───────────────────────────────────────────────────────

    def shell(self, payload: ShellInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)
        if payload.thickness <= self.tolerance:
            return self._invalid_input("Shell thickness must be > tolerance.")

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            faces_to_remove = TopTools_ListOfShape()
            for fid in payload.face_ids:
                parts = fid.split(":face:")
                if len(parts) != 2 or not parts[1].isdigit():
                    return self._invalid_input(f"Invalid face ID format: '{fid}'")
                idx = int(parts[1])
                face = _face_by_index(native, idx)
                faces_to_remove.Append(face)

            thick = BRepOffsetAPI_MakeThickSolid()
            thick.MakeThickSolidByJoin(native, faces_to_remove, -payload.thickness, self.tolerance)
            if not thick.IsDone():
                return make_failure(
                    code=ErrorCode.SHELL_FAILURE,
                    message="Shell operation did not converge.",
                    suggestion="Reduce shell thickness or choose different faces.",
                    failed_check="shell_build",
                )

            result_native = thick.Shape()
            shape = self._register_shape(
                "shell", result_native,
                {"shape_id": payload.shape_id, "face_ids": payload.face_ids, "thickness": payload.thickness},
                source_ids=[meta.id],
            )
            return self._success(shape, "shell")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.SHELL_FAILURE,
                message=f"Shell failed: {exc}",
                suggestion="Reduce shell thickness.",
                failed_check="shell_build",
            )

    # ── Draft ───────────────────────────────────────────────────────

    def draft(self, payload: DraftInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)
        if not payload.face_ids:
            return self._invalid_input("At least one face_id required for draft.")
        if abs(payload.angle) <= self.tolerance or abs(payload.angle) >= 90.0:
            return self._invalid_input("Draft angle must be > 0 and < 90 degrees.")

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            # Use CadQuery's shell-based draft approach for simplicity
            # OCCT draft: BRepOffsetAPI_DraftAngle
            DraftAngle = importlib.import_module("OCP.BRepOffsetAPI").BRepOffsetAPI_DraftAngle
            draft_op = DraftAngle(native)
            pull = gp_Dir(*payload.pull_direction)
            angle_rad = math.radians(payload.angle)

            for fid in payload.face_ids:
                parts = fid.split(":face:")
                if len(parts) != 2 or not parts[1].isdigit():
                    return self._invalid_input(f"Invalid face ID format: '{fid}'")
                idx = int(parts[1])
                face = _face_by_index(native, idx)
                draft_op.Add(face, pull, angle_rad, gp_Pnt(0, 0, 0))

            draft_op.Build()
            if not draft_op.IsDone():
                return make_failure(
                    code=ErrorCode.DRAFT_FAILURE,
                    message="Draft did not converge.",
                    suggestion="Reduce draft angle or choose different faces.",
                    failed_check="draft_build",
                )

            result_native = draft_op.Shape()
            shape = self._register_shape(
                "draft", result_native, payload.model_dump(), source_ids=[meta.id],
            )
            return self._success(shape, "draft")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.DRAFT_FAILURE,
                message=f"Draft failed: {exc}",
                suggestion="Reduce draft angle or adjust face selection.",
                failed_check="draft_build",
            )

    # ── Sketch operations ───────────────────────────────────────────

    def create_sketch(self, payload: CreateSketchInput) -> OperationResult:
        if not payload.segments:
            return self._invalid_input("Sketch must contain at least one segment.")

        try:
            wire_builder = BRepBuilderAPI_MakeWire()
            hole_builders: list[Any] = []

            for seg in payload.segments:
                edge = _sketch_edge(seg, plane=payload.plane, origin=payload.origin)
                if edge is None:
                    continue
                if seg.subtract:
                    hole_builder = BRepBuilderAPI_MakeWire()
                    hole_builder.Add(edge)
                    hole_builders.append(hole_builder)
                else:
                    wire_builder.Add(edge)

            wire_builder.Build()
            if not wire_builder.IsDone():
                return make_failure(
                    code=ErrorCode.SKETCH_ERROR,
                    message="Wire construction failed — check segment connectivity.",
                    suggestion="Ensure segments form a connected chain.",
                    failed_check="wire_build",
                )

            native = wire_builder.Wire()
            if hole_builders:
                face_builder = BRepBuilderAPI_MakeFace(native)
                for hole_builder in hole_builders:
                    hole_builder.Build()
                    if not hole_builder.IsDone():
                        return make_failure(
                            code=ErrorCode.SKETCH_ERROR,
                            message="Hole wire construction failed.",
                            suggestion="Check subtractive sketch segments.",
                            failed_check="hole_wire_build",
                        )
                    # Inner loops must oppose the outer loop orientation so
                    # OCCT treats them as voids rather than additive regions.
                    hole_wire = TopoDS.Wire_s(hole_builder.Wire().Reversed())
                    face_builder.Add(hole_wire)
                face_builder.Build()
                if not face_builder.IsDone():
                    return make_failure(
                        code=ErrorCode.SKETCH_ERROR,
                        message="Profile face construction failed.",
                        suggestion="Ensure subtractive loops are closed and inside the outer profile.",
                        failed_check="profile_face_build",
                    )
                native = face_builder.Face()

            # Store the profile as a wire, or as a face when it contains holes.
            shape_id = self._store.new_id("sketch")
            bbox = _bbox_from_shape(native)
            edge_ids = _edge_list(native, shape_id)
            shape = ShapeData(
                id=shape_id, kind="sketch", parameters=payload.model_dump(),
                bbox=bbox, volume=0.0, manifold=False,
                edge_ids=edge_ids, face_ids=[], source_ids=[],
            )
            self._store.add(shape)
            self._native[shape_id] = native
            return self._success(shape, "create_sketch")

        except Exception as exc:
            return make_failure(
                code=ErrorCode.SKETCH_ERROR,
                message=f"Sketch creation failed: {exc}",
                suggestion="Check segment definitions.",
                failed_check="sketch_build",
            )

    def extrude(self, payload: ExtrudeInput) -> OperationResult:
        meta = self._store.get(payload.sketch_id)
        if not meta:
            return self._shape_not_found(payload.sketch_id)
        if abs(payload.distance) <= self.tolerance:
            return self._invalid_input("Extrude distance must be non-zero.")

        native = self._get_native(payload.sketch_id)
        if native is None:
            return self._shape_not_found(payload.sketch_id)

        try:
            # Holed sketches are already faces; simple profiles remain wires.
            if native.ShapeType() == TopAbs_FACE:
                face = TopoDS.Face_s(native)
            else:
                face = BRepBuilderAPI_MakeFace(native).Face()
            vec = gp_Vec(0, 0, payload.distance)
            if payload.both:
                vec_neg = gp_Vec(0, 0, -payload.distance)
                prism_mod = importlib.import_module("OCP.BRepPrimAPI")
                solid_pos = prism_mod.BRepPrimAPI_MakePrism(face, vec).Shape()
                solid_neg = prism_mod.BRepPrimAPI_MakePrism(face, vec_neg).Shape()
                result_native = BRepAlgoAPI_Fuse(solid_pos, solid_neg).Shape()
            else:
                prism_mod = importlib.import_module("OCP.BRepPrimAPI")
                result_native = prism_mod.BRepPrimAPI_MakePrism(face, vec).Shape()

            shape = self._register_shape(
                "extrude", result_native, payload.model_dump(), source_ids=[meta.id],
            )
            return self._success(shape, "extrude")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.EXTRUDE_FAILURE,
                message=f"Extrude failed: {exc}",
                suggestion="Ensure the sketch forms a closed profile.",
                failed_check="extrude_build",
            )

    # ── Revolve ─────────────────────────────────────────────────────

    def revolve(self, payload: RevolveInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)
        if abs(payload.angle) <= self.tolerance:
            return self._invalid_input("Revolve angle must be non-zero.")

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            # If it's a wire, make a face first
            try:
                face = BRepBuilderAPI_MakeFace(native).Face()
                profile = face
            except Exception:
                profile = native

            ax = gp_Ax1(
                gp_Pnt(*payload.axis_origin),
                gp_Dir(*payload.axis_direction),
            )
            angle_rad = math.radians(payload.angle)
            result_native = BRepPrimAPI_MakeRevol(profile, ax, angle_rad).Shape()

            shape = self._register_shape(
                "revolve", result_native, payload.model_dump(), source_ids=[meta.id],
            )
            return self._success(shape, "revolve")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.REVOLVE_FAILURE,
                message=f"Revolve failed: {exc}",
                suggestion="Ensure profile doesn't cross the revolution axis.",
                failed_check="revolve_build",
            )

    # ── Sweep ───────────────────────────────────────────────────────

    def sweep(self, payload: SweepInput) -> OperationResult:
        profile_meta = self._store.get(payload.profile_id)
        if not profile_meta:
            return self._shape_not_found(payload.profile_id)
        path_meta = self._store.get(payload.path_id)
        if not path_meta:
            return self._shape_not_found(payload.path_id)

        profile_native = self._get_native(payload.profile_id)
        path_native = self._get_native(payload.path_id)
        if profile_native is None or path_native is None:
            return self._shape_not_found(payload.profile_id)

        try:
            # Get wire from path
            path_wire = _wire_by_index(path_native, 0) if TopExp_Explorer(path_native, TopAbs_WIRE).More() else path_native

            # Make face from profile if it's a wire
            try:
                profile_face = BRepBuilderAPI_MakeFace(profile_native).Face()
            except Exception:
                profile_face = profile_native

            pipe = BRepOffsetAPI_MakePipe(path_wire, profile_face)
            if not pipe.IsDone():
                return make_failure(
                    code=ErrorCode.SWEEP_FAILURE,
                    message="Sweep (pipe) did not converge.",
                    suggestion="Ensure profile and path are compatible.",
                    failed_check="sweep_build",
                )

            result_native = pipe.Shape()
            shape = self._register_shape(
                "sweep", result_native, payload.model_dump(),
                source_ids=[profile_meta.id, path_meta.id],
            )
            return self._success(shape, "sweep")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.SWEEP_FAILURE,
                message=f"Sweep failed: {exc}",
                suggestion="Check profile and path compatibility.",
                failed_check="sweep_build",
            )

    # ── Loft ────────────────────────────────────────────────────────

    def loft(self, payload: LoftInput) -> OperationResult:
        profiles: list[tuple[Any, Any]] = []
        profile_ids: list[str] = []
        for pid in payload.profile_ids:
            meta = self._store.get(pid)
            if not meta:
                return self._shape_not_found(pid)
            native = self._get_native(pid)
            if native is None:
                return self._shape_not_found(pid)
            profiles.append((meta, native))
            profile_ids.append(meta.id)

        try:
            loft_op = BRepOffsetAPI_ThruSections(payload.solid, payload.ruled)
            for _, native in profiles:
                # Add wire(s) from each profile
                explorer = TopExp_Explorer(native, TopAbs_WIRE)
                if explorer.More():
                    wire = TopoDS.Wire_s(explorer.Current())
                    loft_op.AddWire(wire)
                else:
                    # Try as a single vertex / edge
                    loft_op.AddWire(native)

            loft_op.Build()
            if not loft_op.IsDone():
                return make_failure(
                    code=ErrorCode.LOFT_FAILURE,
                    message="Loft (ThruSections) did not converge.",
                    suggestion="Ensure profiles are compatible for lofting.",
                    failed_check="loft_build",
                )

            result_native = loft_op.Shape()
            shape = self._register_shape(
                "loft", result_native, payload.model_dump(), source_ids=profile_ids,
            )
            return self._success(shape, "loft")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.LOFT_FAILURE,
                message=f"Loft failed: {exc}",
                suggestion="Check that profiles are compatible.",
                failed_check="loft_build",
            )

    # ── Linear pattern ──────────────────────────────────────────────

    def linear_pattern(self, payload: LinearPatternInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)
        if payload.spacing <= self.tolerance:
            return self._invalid_input("Pattern spacing must be > tolerance.")

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            d = payload.direction
            ln = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
            if ln < 1e-12:
                return self._invalid_input("Direction vector must be non-zero.")
            dx, dy, dz = d[0] / ln, d[1] / ln, d[2] / ln

            result = native
            for i in range(1, payload.count):
                trsf = gp_Trsf()
                trsf.SetTranslation(gp_Vec(
                    dx * payload.spacing * i,
                    dy * payload.spacing * i,
                    dz * payload.spacing * i,
                ))
                copy = BRepBuilderAPI_Transform(native, trsf, True).Shape()
                result = BRepAlgoAPI_Fuse(result, copy).Shape()

            shape = self._register_shape(
                "linear_pattern", result, payload.model_dump(), source_ids=[meta.id],
            )
            return self._success(shape, "linear_pattern")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.PATTERN_ERROR,
                message=f"Linear pattern failed: {exc}",
                suggestion="Check spacing and direction values.",
                failed_check="pattern_build",
            )

    # ── Circular pattern ────────────────────────────────────────────

    def circular_pattern(self, payload: CircularPatternInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            ax_dir = payload.axis_direction
            step_angle = math.radians(payload.angle) / payload.count

            result = native
            for i in range(1, payload.count):
                trsf = gp_Trsf()
                trsf.SetRotation(
                    gp_Ax1(gp_Pnt(*payload.axis_origin), gp_Dir(*ax_dir)),
                    step_angle * i,
                )
                copy = BRepBuilderAPI_Transform(native, trsf, True).Shape()
                result = BRepAlgoAPI_Fuse(result, copy).Shape()

            shape = self._register_shape(
                "circular_pattern", result, payload.model_dump(), source_ids=[meta.id],
            )
            return self._success(shape, "circular_pattern")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.PATTERN_ERROR,
                message=f"Circular pattern failed: {exc}",
                suggestion="Check axis and angle values.",
                failed_check="pattern_build",
            )

    # ── Mirror ──────────────────────────────────────────────────────

    def mirror(self, payload: MirrorInput) -> OperationResult:
        meta = self._store.get(payload.shape_id)
        if not meta:
            return self._shape_not_found(payload.shape_id)

        native = self._get_native(payload.shape_id)
        if native is None:
            return self._shape_not_found(payload.shape_id)

        try:
            ax = gp_Ax2(gp_Pnt(*payload.plane_origin), gp_Dir(*payload.plane_normal))
            trsf = gp_Trsf()
            trsf.SetMirror(ax)
            mirrored = BRepBuilderAPI_Transform(native, trsf, True).Shape()
            result = BRepAlgoAPI_Fuse(native, mirrored).Shape()

            shape = self._register_shape(
                "mirror", result, payload.model_dump(), source_ids=[meta.id],
            )
            return self._success(shape, "mirror")
        except Exception as exc:
            return make_failure(
                code=ErrorCode.MIRROR_FAILURE,
                message=f"Mirror failed: {exc}",
                suggestion="Check plane definition.",
                failed_check="mirror_build",
            )

    # ── Topology naming ─────────────────────────────────────────────

    def get_topology(self, shape_id: str) -> TopologyMap:
        """Build a real topology map from the native OCCT shape."""
        native = self._get_native(shape_id)
        if native is None:
            raise ValueError(f"Shape '{shape_id}' not found.")
        return _build_topology_map(native, shape_id)
