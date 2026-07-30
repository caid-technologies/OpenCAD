"""Tests for new operation families (chamfer, shell, draft, cone, torus,
sketch, extrude, revolve, sweep, loft, patterns, mirror) and topology naming.

These tests run against the *analytic* backend (no OCCT required).
"""

from __future__ import annotations

import pytest

from opencad_kernel.core.errors import Failure
from opencad_kernel.core.models import Success, TopologyMap
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.registry import OperationRegistry
from opencad_kernel.operations.schemas import (
    ChamferEdgesInput,
    CircularPatternInput,
    CreateBoxInput,
    CreateConeInput,
    CreateCylinderInput,
    CreateSketchInput,
    CreateSphereInput,
    CreateTorusInput,
    DraftInput,
    ExtrudeInput,
    LinearPatternInput,
    LoftInput,
    MirrorInput,
    RevolveInput,
    SelectorQuery,
    ShellInput,
    SketchSegment,
    SweepInput,
)


@pytest.fixture()
def kernel() -> OpenCadKernel:
    return OpenCadKernel(tolerance=1e-6, id_strategy="readable")


@pytest.fixture()
def registry(kernel: OpenCadKernel) -> OperationRegistry:
    return OperationRegistry(kernel)


# ── Additional primitives ───────────────────────────────────────────


class TestCreateCone:
    def test_create_cone(self, kernel: OpenCadKernel) -> None:
        r = kernel.create_cone(CreateConeInput(radius1=2.0, radius2=0.5, height=5.0))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "cone"
        assert r.shape.volume > 0

    def test_cone_zero_height(self, kernel: OpenCadKernel) -> None:
        r = kernel.create_cone(CreateConeInput(radius1=1.0, radius2=0.0, height=0.0))
        assert isinstance(r, Failure)

    def test_cone_both_radii_zero(self, kernel: OpenCadKernel) -> None:
        r = kernel.create_cone(CreateConeInput(radius1=0.0, radius2=0.0, height=5.0))
        assert isinstance(r, Failure)


class TestCreateTorus:
    def test_create_torus(self, kernel: OpenCadKernel) -> None:
        r = kernel.create_torus(CreateTorusInput(major_radius=5.0, minor_radius=1.0))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "torus"
        assert r.shape.volume > 0

    def test_torus_minor_ge_major(self, kernel: OpenCadKernel) -> None:
        r = kernel.create_torus(CreateTorusInput(major_radius=2.0, minor_radius=3.0))
        assert isinstance(r, Failure)


# ── Chamfer ─────────────────────────────────────────────────────────


class TestChamfer:
    def test_chamfer_edges(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success) and box.shape is not None
        edge_id = box.shape.edge_ids[0]
        r = kernel.chamfer_edges(ChamferEdgesInput(shape_id=box.shape_id, edge_ids=[edge_id], distance=1.0))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "chamfer"

    def test_chamfer_no_edges(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success)
        r = kernel.chamfer_edges(ChamferEdgesInput(shape_id=box.shape_id, edge_ids=[], distance=1.0))
        assert isinstance(r, Failure)

    def test_chamfer_zero_distance(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.chamfer_edges(ChamferEdgesInput(shape_id=box.shape_id, edge_ids=[box.shape.edge_ids[0]], distance=0.0))
        assert isinstance(r, Failure)


# ── Shell ───────────────────────────────────────────────────────────


class TestShell:
    def test_shell(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.shell(ShellInput(shape_id=box.shape_id, face_ids=[box.shape.face_ids[0]], thickness=1.0))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "shell"
        assert r.shape.volume < box.shape.volume

    def test_shell_too_thick(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=4, width=4, height=4))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.shell(ShellInput(shape_id=box.shape_id, face_ids=[], thickness=3.0))
        assert isinstance(r, Failure)


# ── Draft ───────────────────────────────────────────────────────────


class TestDraft:
    def test_draft(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.draft(DraftInput(shape_id=box.shape_id, face_ids=[box.shape.face_ids[0]], angle=5.0))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "draft"

    def test_draft_zero_angle(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.draft(DraftInput(shape_id=box.shape_id, face_ids=[box.shape.face_ids[0]], angle=0.0))
        assert isinstance(r, Failure)

    def test_draft_90_degrees(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.draft(DraftInput(shape_id=box.shape_id, face_ids=[box.shape.face_ids[0]], angle=90.0))
        assert isinstance(r, Failure)


# ── Sketch + Extrude ────────────────────────────────────────────────


class TestSketch:
    def _square_sketch(self, kernel: OpenCadKernel) -> Success:
        segments = [
            SketchSegment(type="line", start=(0, 0), end=(10, 0)),
            SketchSegment(type="line", start=(10, 0), end=(10, 10)),
            SketchSegment(type="line", start=(10, 10), end=(0, 10)),
            SketchSegment(type="line", start=(0, 10), end=(0, 0)),
        ]
        r = kernel.create_sketch(CreateSketchInput(segments=segments))
        assert isinstance(r, Success)
        return r

    def test_create_sketch(self, kernel: OpenCadKernel) -> None:
        r = self._square_sketch(kernel)
        assert r.shape is not None
        assert r.shape.kind == "sketch"
        assert r.shape.volume == 0.0
        assert r.shape.manifold is False

    def test_sketch_empty(self, kernel: OpenCadKernel) -> None:
        r = kernel.create_sketch(CreateSketchInput(segments=[]))
        assert isinstance(r, Failure)

    def test_sketch_circle(self, kernel: OpenCadKernel) -> None:
        r = kernel.create_sketch(CreateSketchInput(
            segments=[SketchSegment(type="circle", center=(0, 0), radius=5.0)]
        ))
        assert isinstance(r, Success)

    def test_extrude(self, kernel: OpenCadKernel) -> None:
        sk = self._square_sketch(kernel)
        r = kernel.extrude(ExtrudeInput(sketch_id=sk.shape_id, distance=5.0))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "extrude"
        assert r.shape.volume > 0

    def test_extrude_both(self, kernel: OpenCadKernel) -> None:
        sk = self._square_sketch(kernel)
        r = kernel.extrude(ExtrudeInput(sketch_id=sk.shape_id, distance=5.0, both=True))
        assert isinstance(r, Success)

    def test_extrude_zero(self, kernel: OpenCadKernel) -> None:
        sk = self._square_sketch(kernel)
        r = kernel.extrude(ExtrudeInput(sketch_id=sk.shape_id, distance=0.0))
        assert isinstance(r, Failure)


# ── Revolve ─────────────────────────────────────────────────────────


class TestRevolve:
    def test_revolve(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=2, width=2, height=2))
        assert isinstance(box, Success)
        r = kernel.revolve(RevolveInput(shape_id=box.shape_id, angle=180.0))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "revolve"

    def test_revolve_zero_angle(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=2, width=2, height=2))
        assert isinstance(box, Success)
        r = kernel.revolve(RevolveInput(shape_id=box.shape_id, angle=0.0))
        assert isinstance(r, Failure)


# ── Sweep ───────────────────────────────────────────────────────────


class TestSweep:
    def test_sweep(self, kernel: OpenCadKernel) -> None:
        profile = kernel.create_box(CreateBoxInput(length=2, width=2, height=2))
        path = kernel.create_cylinder(CreateCylinderInput(radius=1, height=10))
        assert isinstance(profile, Success) and isinstance(path, Success)
        r = kernel.sweep(SweepInput(profile_id=profile.shape_id, path_id=path.shape_id))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "sweep"

    def test_sweep_missing_profile(self, kernel: OpenCadKernel) -> None:
        path = kernel.create_cylinder(CreateCylinderInput(radius=1, height=10))
        assert isinstance(path, Success)
        r = kernel.sweep(SweepInput(profile_id="nonexistent", path_id=path.shape_id))
        assert isinstance(r, Failure)


# ── Loft ────────────────────────────────────────────────────────────


class TestLoft:
    def test_loft(self, kernel: OpenCadKernel) -> None:
        p1 = kernel.create_box(CreateBoxInput(length=4, width=4, height=1))
        p2 = kernel.create_box(CreateBoxInput(length=2, width=2, height=1))
        assert isinstance(p1, Success) and isinstance(p2, Success)
        r = kernel.loft(LoftInput(profile_ids=[p1.shape_id, p2.shape_id]))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "loft"

    def test_loft_missing_profile(self, kernel: OpenCadKernel) -> None:
        p1 = kernel.create_box(CreateBoxInput(length=4, width=4, height=1))
        assert isinstance(p1, Success)
        r = kernel.loft(LoftInput(profile_ids=[p1.shape_id, "nonexistent"]))
        assert isinstance(r, Failure)


# ── Linear pattern ──────────────────────────────────────────────────


class TestLinearPattern:
    def test_linear_pattern(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=2, width=2, height=2))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.linear_pattern(LinearPatternInput(
            shape_id=box.shape_id, direction=(1, 0, 0), count=3, spacing=5.0,
        ))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "linear_pattern"
        assert r.shape.volume == box.shape.volume * 3

    def test_linear_pattern_zero_spacing(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=2, width=2, height=2))
        assert isinstance(box, Success)
        r = kernel.linear_pattern(LinearPatternInput(
            shape_id=box.shape_id, direction=(1, 0, 0), count=3, spacing=0.0,
        ))
        assert isinstance(r, Failure)


# ── Circular pattern ────────────────────────────────────────────────


class TestCircularPattern:
    def test_circular_pattern(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=2, width=2, height=2))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.circular_pattern(CircularPatternInput(
            shape_id=box.shape_id, count=4, angle=360.0,
        ))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "circular_pattern"
        assert r.shape.volume == box.shape.volume * 4


# ── Mirror ──────────────────────────────────────────────────────────


class TestMirror:
    def test_mirror(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=2, width=2, height=2))
        assert isinstance(box, Success) and box.shape is not None
        r = kernel.mirror(MirrorInput(shape_id=box.shape_id, plane_normal=(1, 0, 0)))
        assert isinstance(r, Success)
        assert r.shape is not None
        assert r.shape.kind == "mirror"
        assert r.shape.volume == box.shape.volume * 2


# ── Topology naming ─────────────────────────────────────────────────


class TestTopology:
    def test_box_topology(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success) and box.shape is not None
        topo = kernel.get_topology(box.shape_id)
        assert isinstance(topo, TopologyMap)
        assert topo.shape_id == box.shape_id
        assert len(topo.faces) == 6
        assert len(topo.edges) == 12

    def test_box_face_tags(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success)
        topo = kernel.get_topology(box.shape_id)
        all_tags = set()
        for face in topo.faces:
            all_tags.update(face.tags)
        # Should have directional tags
        assert "top" in all_tags
        assert "bottom" in all_tags

    def test_cylinder_topology(self, kernel: OpenCadKernel) -> None:
        cyl = kernel.create_cylinder(CreateCylinderInput(radius=5, height=10))
        assert isinstance(cyl, Success)
        topo = kernel.get_topology(cyl.shape_id)
        assert len(topo.faces) == 3  # top, bottom, lateral
        assert any("top" in f.tags for f in topo.faces)

    def test_sphere_topology(self, kernel: OpenCadKernel) -> None:
        sph = kernel.create_sphere(CreateSphereInput(radius=5))
        assert isinstance(sph, Success)
        topo = kernel.get_topology(sph.shape_id)
        assert len(topo.faces) == 1

    def test_topology_not_found(self, kernel: OpenCadKernel) -> None:
        with pytest.raises(ValueError):
            kernel.get_topology("nonexistent")


# ── Selector queries ────────────────────────────────────────────────


class TestSelectors:
    def test_select_top_face(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success)
        results = kernel.select_subshapes(box.shape_id, SelectorQuery(
            kind="face", tags=["top"],
        ))
        assert len(results) == 1
        assert "top" in results[0].tags

    def test_select_by_direction(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success)
        results = kernel.select_subshapes(box.shape_id, SelectorQuery(
            kind="face", direction=(0, 0, 1), direction_tolerance=0.1,
        ))
        assert len(results) == 1
        assert "top" in results[0].tags

    def test_select_sort_by_z(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success)
        results = kernel.select_subshapes(box.shape_id, SelectorQuery(
            kind="face", sort_by="z", sort_reverse=True,
        ))
        assert len(results) == 6
        # First face should be the "top" one (highest Z centroid)
        assert results[0].centroid[2] >= results[-1].centroid[2]

    def test_select_with_limit(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success)
        results = kernel.select_subshapes(box.shape_id, SelectorQuery(
            kind="face", sort_by="z", sort_reverse=True, limit=1,
        ))
        assert len(results) == 1

    def test_select_edges(self, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        assert isinstance(box, Success)
        results = kernel.select_subshapes(box.shape_id, SelectorQuery(kind="edge"))
        assert len(results) == 12


# ── Registry lists new operations ───────────────────────────────────


class TestRegistryNewOps:
    def test_new_ops_registered(self, registry: OperationRegistry) -> None:
        ops = registry.list_operations()
        expected_new = [
            "create_cone", "create_torus",
            "chamfer_edges", "shell", "draft",
            "create_sketch", "extrude",
            "revolve", "sweep", "loft",
            "linear_pattern", "circular_pattern", "mirror",
        ]
        for op in expected_new:
            assert op in ops, f"Expected '{op}' in registered operations"

    def test_new_ops_have_schemas(self, registry: OperationRegistry) -> None:
        for op in ["chamfer_edges", "shell", "draft", "loft", "revolve", "mirror"]:
            schema = registry.get_json_schema(op)
            assert "properties" in schema
            assert "x-opencad-version" in schema

    def test_call_cone_via_registry(self, registry: OperationRegistry) -> None:
        result = registry.call("create_cone", {"radius1": 2.0, "radius2": 0.5, "height": 5.0})
        assert isinstance(result, Success)


# ── API topology endpoints ──────────────────────────────────────────


class TestTopologyAPI:
    def test_get_topology_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from opencad_kernel.api import app

        client = TestClient(app)
        # Create a box
        resp = client.post("/operations/create_box", json={"payload": {"length": 5, "width": 5, "height": 5}})
        assert resp.status_code == 200
        shape_id = resp.json()["shape_id"]

        # Get topology
        topo_resp = client.get(f"/shapes/{shape_id}/topology")
        assert topo_resp.status_code == 200
        topo = topo_resp.json()
        assert topo["shape_id"] == shape_id
        assert len(topo["faces"]) > 0

    def test_get_faces_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from opencad_kernel.api import app

        client = TestClient(app)
        resp = client.post("/operations/create_box", json={"payload": {"length": 5, "width": 5, "height": 5}})
        shape_id = resp.json()["shape_id"]

        faces_resp = client.get(f"/shapes/{shape_id}/faces")
        assert faces_resp.status_code == 200
        faces = faces_resp.json()
        assert len(faces) == 6

    def test_select_endpoint(self) -> None:
        from fastapi.testclient import TestClient
        from opencad_kernel.api import app

        client = TestClient(app)
        resp = client.post("/operations/create_box", json={"payload": {"length": 5, "width": 5, "height": 5}})
        shape_id = resp.json()["shape_id"]

        sel_resp = client.post(f"/shapes/{shape_id}/select", json={
            "kind": "face", "tags": ["top"],
        })
        assert sel_resp.status_code == 200
        results = sel_resp.json()
        assert len(results) == 1
        assert "top" in results[0]["tags"]

    def test_topology_not_found(self) -> None:
        from fastapi.testclient import TestClient
        from opencad_kernel.api import app

        client = TestClient(app)
        resp = client.get("/shapes/nonexistent/topology")
        assert resp.status_code == 404


# ── Assembly mates (3-D constraints — Phase 1) ─────────────────────


class TestAssemblyMates:
    def test_create_coincident_mate(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import AssemblyMateType, CreateAssemblyMateInput

        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        cyl = kernel.create_cylinder(CreateCylinderInput(radius=3, height=10))
        assert isinstance(box, Success) and isinstance(cyl, Success)
        assert box.shape is not None and cyl.shape is not None

        r = kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.COINCIDENT,
            entity_a=f"{box.shape.id}:face:0",
            entity_b=f"{cyl.shape.id}:face:0",
        ))
        assert isinstance(r, Success)
        assert r.metadata["mate_id"] is not None
        assert r.metadata["mate"]["type"] == "coincident"
        assert r.metadata["mate"]["status"] == "pending"

    def test_create_distance_mate(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import AssemblyMateType, CreateAssemblyMateInput

        b1 = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        b2 = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        assert isinstance(b1, Success) and isinstance(b2, Success)
        assert b1.shape is not None and b2.shape is not None

        r = kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.DISTANCE,
            entity_a=f"{b1.shape.id}:face:0",
            entity_b=f"{b2.shape.id}:face:0",
            value=5.0,
        ))
        assert isinstance(r, Success)
        assert r.metadata["mate"]["value"] == 5.0

    def test_distance_mate_requires_value(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import AssemblyMateType, CreateAssemblyMateInput

        box = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        assert isinstance(box, Success) and box.shape is not None

        r = kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.DISTANCE,
            entity_a=f"{box.shape.id}:face:0",
            entity_b=f"{box.shape.id}:face:1",
        ))
        assert isinstance(r, Failure)
        assert "value" in r.message.lower()

    def test_mate_invalid_entity_a(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import AssemblyMateType, CreateAssemblyMateInput

        box = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        assert isinstance(box, Success) and box.shape is not None

        r = kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.COINCIDENT,
            entity_a="nonexistent:face:0",
            entity_b=f"{box.shape.id}:face:0",
        ))
        assert isinstance(r, Failure)
        assert r.code.value == "MATE_INVALID_REFERENCE"

    def test_mate_invalid_entity_b(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import AssemblyMateType, CreateAssemblyMateInput

        box = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        assert isinstance(box, Success) and box.shape is not None

        r = kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.COINCIDENT,
            entity_a=f"{box.shape.id}:face:0",
            entity_b="nonexistent:face:0",
        ))
        assert isinstance(r, Failure)

    def test_duplicate_mate_rejected(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import AssemblyMateType, CreateAssemblyMateInput

        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        cyl = kernel.create_cylinder(CreateCylinderInput(radius=3, height=10))
        assert isinstance(box, Success) and isinstance(cyl, Success)
        assert box.shape is not None and cyl.shape is not None

        inp = CreateAssemblyMateInput(
            type=AssemblyMateType.PARALLEL,
            entity_a=f"{box.shape.id}:face:0",
            entity_b=f"{cyl.shape.id}:face:0",
        )
        r1 = kernel.create_assembly_mate(inp)
        assert isinstance(r1, Success)
        r2 = kernel.create_assembly_mate(inp)
        assert isinstance(r2, Failure)
        assert r2.code.value == "MATE_DUPLICATE"

    def test_delete_mate(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import (
            AssemblyMateType,
            CreateAssemblyMateInput,
            DeleteAssemblyMateInput,
        )

        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        cyl = kernel.create_cylinder(CreateCylinderInput(radius=3, height=10))
        assert isinstance(box, Success) and isinstance(cyl, Success)
        assert box.shape is not None and cyl.shape is not None

        create_r = kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.COINCIDENT,
            entity_a=f"{box.shape.id}:face:0",
            entity_b=f"{cyl.shape.id}:face:0",
        ))
        assert isinstance(create_r, Success)
        mate_id = create_r.metadata["mate_id"]

        del_r = kernel.delete_assembly_mate(DeleteAssemblyMateInput(mate_id=mate_id))
        assert isinstance(del_r, Success)

    def test_delete_nonexistent_mate(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import DeleteAssemblyMateInput

        r = kernel.delete_assembly_mate(DeleteAssemblyMateInput(mate_id="nope"))
        assert isinstance(r, Failure)
        assert r.code.value == "MATE_NOT_FOUND"

    def test_list_mates(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import (
            AssemblyMateType,
            CreateAssemblyMateInput,
            ListAssemblyMatesInput,
        )

        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        cyl = kernel.create_cylinder(CreateCylinderInput(radius=3, height=10))
        assert isinstance(box, Success) and isinstance(cyl, Success)
        assert box.shape is not None and cyl.shape is not None

        kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.COINCIDENT,
            entity_a=f"{box.shape.id}:face:0",
            entity_b=f"{cyl.shape.id}:face:0",
        ))
        kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.PARALLEL,
            entity_a=f"{box.shape.id}:face:1",
            entity_b=f"{cyl.shape.id}:face:1",
        ))

        r = kernel.list_assembly_mates(ListAssemblyMatesInput())
        assert isinstance(r, Success)
        assert len(r.metadata["mates"]) == 2

    def test_list_mates_filtered_by_entity(self, kernel: OpenCadKernel) -> None:
        from opencad_kernel.operations.schemas import (
            AssemblyMateType,
            CreateAssemblyMateInput,
            ListAssemblyMatesInput,
        )

        b1 = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        b2 = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        b3 = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
        assert isinstance(b1, Success) and isinstance(b2, Success) and isinstance(b3, Success)
        assert b1.shape is not None and b2.shape is not None and b3.shape is not None

        ref_a = f"{b1.shape.id}:face:0"
        kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.COINCIDENT,
            entity_a=ref_a,
            entity_b=f"{b2.shape.id}:face:0",
        ))
        kernel.create_assembly_mate(CreateAssemblyMateInput(
            type=AssemblyMateType.COINCIDENT,
            entity_a=f"{b2.shape.id}:face:1",
            entity_b=f"{b3.shape.id}:face:0",
        ))

        r = kernel.list_assembly_mates(ListAssemblyMatesInput(entity_ref=ref_a))
        assert isinstance(r, Success)
        assert len(r.metadata["mates"]) == 1

    def test_all_mate_types(self, kernel: OpenCadKernel) -> None:
        """Ensure every AssemblyMateType can be created."""
        from opencad_kernel.operations.schemas import AssemblyMateType, CreateAssemblyMateInput

        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        cyl = kernel.create_cylinder(CreateCylinderInput(radius=3, height=10))
        assert isinstance(box, Success) and isinstance(cyl, Success)
        assert box.shape is not None and cyl.shape is not None

        for i, mtype in enumerate(AssemblyMateType):
            value = 5.0 if mtype in (AssemblyMateType.DISTANCE, AssemblyMateType.ANGLE) else None
            r = kernel.create_assembly_mate(CreateAssemblyMateInput(
                type=mtype,
                entity_a=f"{box.shape.id}:face:{i % 6}",
                entity_b=f"{cyl.shape.id}:face:{i % 3}",
                value=value,
            ))
            assert isinstance(r, Success), f"Failed for mate type {mtype}"


class TestAssemblyMateRegistry:
    def test_mate_ops_registered(self, registry: OperationRegistry) -> None:
        ops = registry.list_operations()
        assert "create_assembly_mate" in ops
        assert "delete_assembly_mate" in ops
        assert "list_assembly_mates" in ops

    def test_mate_ops_have_schemas(self, registry: OperationRegistry) -> None:
        for op in ["create_assembly_mate", "delete_assembly_mate", "list_assembly_mates"]:
            schema = registry.get_json_schema(op)
            assert "properties" in schema

    def test_call_create_mate_via_registry(self, registry: OperationRegistry, kernel: OpenCadKernel) -> None:
        box = kernel.create_box(CreateBoxInput(length=10, width=10, height=10))
        cyl = kernel.create_cylinder(CreateCylinderInput(radius=3, height=10))
        assert isinstance(box, Success) and isinstance(cyl, Success)
        assert box.shape is not None and cyl.shape is not None

        result = registry.call("create_assembly_mate", {
            "type": "coincident",
            "entity_a": f"{box.shape.id}:face:0",
            "entity_b": f"{cyl.shape.id}:face:0",
        })
        assert isinstance(result, Success)
