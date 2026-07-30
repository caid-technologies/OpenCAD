"""Tests for the OCCT backend.

These tests are skipped if CadQuery/OCP is not installed.
Run with: pytest opencad_kernel/tests/test_occt_backend.py
"""

from __future__ import annotations

import importlib.util
import pytest

HAS_OCCT = (
    importlib.util.find_spec("cadquery") is not None
    and importlib.util.find_spec("OCP") is not None
)

pytestmark = pytest.mark.skipif(not HAS_OCCT, reason="CadQuery/OCP not installed")


@pytest.fixture()
def backend():
    from opencad_kernel.core.occt_backend import OcctBackend

    return OcctBackend(tolerance=1e-6, id_strategy="readable")


# ── Primitive creation ──────────────────────────────────────────────


def test_create_box(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput

    result = backend.create_box(CreateBoxInput(length=10.0, width=5.0, height=3.0))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume == pytest.approx(150.0, rel=0.01)
    assert result.shape.bbox.min_x < result.shape.bbox.max_x
    assert len(result.shape.edge_ids) == 12  # A box has 12 edges


def test_create_cylinder(backend):
    from math import pi

    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateCylinderInput

    result = backend.create_cylinder(CreateCylinderInput(radius=2.0, height=5.0))
    assert isinstance(result, Success)
    assert result.shape is not None
    expected = pi * 4.0 * 5.0
    assert result.shape.volume == pytest.approx(expected, rel=0.01)


def test_create_sphere(backend):
    from math import pi

    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateSphereInput

    result = backend.create_sphere(CreateSphereInput(radius=3.0))
    assert isinstance(result, Success)
    assert result.shape is not None
    expected = (4.0 / 3.0) * pi * 27.0
    assert result.shape.volume == pytest.approx(expected, rel=0.01)


def test_create_box_invalid(backend):
    from opencad_kernel.core.errors import ErrorCode, Failure
    from opencad_kernel.operations.schemas import CreateBoxInput

    result = backend.create_box(CreateBoxInput(length=-1.0, width=2.0, height=3.0))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.INVALID_INPUT


# ── Boolean operations ──────────────────────────────────────────────


def _make_two_boxes(backend, offset: float = 0.0):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput

    a = backend.create_box(CreateBoxInput(length=2.0, width=2.0, height=2.0))
    b = backend.create_box(CreateBoxInput(length=2.0, width=2.0, height=2.0))
    assert isinstance(a, Success) and isinstance(b, Success)
    return a.shape_id, b.shape_id


def test_boolean_union(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import BooleanInput

    a_id, b_id = _make_two_boxes(backend)
    result = backend.boolean_union(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > 0.0


def test_boolean_cut(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import BooleanInput, CreateBoxInput

    a = backend.create_box(CreateBoxInput(length=10.0, width=10.0, height=10.0))
    b = backend.create_box(CreateBoxInput(length=5.0, width=5.0, height=5.0))
    assert isinstance(a, Success) and isinstance(b, Success)

    result = backend.boolean_cut(BooleanInput(shape_a_id=a.shape_id, shape_b_id=b.shape_id))
    assert isinstance(result, Success)
    assert result.shape is not None
    # Cutting a 5x5x5 from a 10x10x10 leaves less than 1000
    assert result.shape.volume < 1000.0
    assert result.shape.volume > 0.0


def test_boolean_intersection(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import BooleanInput

    a_id, b_id = _make_two_boxes(backend)
    result = backend.boolean_intersection(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > 0.0


def test_boolean_shape_not_found(backend):
    from opencad_kernel.core.errors import ErrorCode, Failure
    from opencad_kernel.operations.schemas import BooleanInput

    result = backend.boolean_union(BooleanInput(shape_a_id="missing", shape_b_id="also"))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.SHAPE_NOT_FOUND


# ── Fillet ──────────────────────────────────────────────────────────


def test_fillet_edges(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput, FilletEdgesInput

    box = backend.create_box(CreateBoxInput(length=10.0, width=10.0, height=10.0))
    assert isinstance(box, Success) and box.shape is not None
    edge_id = box.shape.edge_ids[0]

    result = backend.fillet_edges(FilletEdgesInput(shape_id=box.shape_id, edge_ids=[edge_id], radius=1.0))
    assert isinstance(result, Success)
    assert result.shape is not None
    # Fillet removes a bit of volume
    assert result.shape.volume < box.shape.volume


def test_fillet_no_edges(backend):
    from opencad_kernel.core.errors import ErrorCode, Failure
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput, FilletEdgesInput

    box = backend.create_box(CreateBoxInput(length=5.0, width=5.0, height=5.0))
    assert isinstance(box, Success)
    result = backend.fillet_edges(FilletEdgesInput(shape_id=box.shape_id, edge_ids=[], radius=0.5))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.INVALID_INPUT


# ── Tessellation ────────────────────────────────────────────────────


def test_tessellate_box(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput

    box = backend.create_box(CreateBoxInput(length=5.0, width=5.0, height=5.0))
    assert isinstance(box, Success) and box.shape_id

    mesh = backend.tessellate(box.shape_id, deflection=0.1)
    assert len(mesh.vertices) > 0
    assert len(mesh.faces) > 0
    assert len(mesh.normals) > 0
    # Each vertex is 3 floats
    assert len(mesh.vertices) % 3 == 0
    # Each face is 3 indices
    assert len(mesh.faces) % 3 == 0


def test_tessellate_cylinder(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateCylinderInput

    cyl = backend.create_cylinder(CreateCylinderInput(radius=2.0, height=5.0))
    assert isinstance(cyl, Success) and cyl.shape_id

    mesh = backend.tessellate(cyl.shape_id, deflection=0.1)
    assert len(mesh.vertices) > 0
    assert len(mesh.faces) > 0


def test_tessellate_missing_shape(backend):
    with pytest.raises(ValueError, match="not found"):
        backend.tessellate("nonexistent")


def test_tessellate_face_streaming(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput

    box = backend.create_box(CreateBoxInput(length=5.0, width=5.0, height=5.0))
    assert isinstance(box, Success) and box.shape_id

    total = backend.count_faces(box.shape_id)
    assert total == 6  # A box has 6 faces

    all_verts = []
    for i in range(total):
        mesh_chunk, t = backend.tessellate_face(box.shape_id, i, deflection=0.1)
        assert t == total
        all_verts.extend(mesh_chunk.vertices)

    # Full tessellation should have the same vertex data
    full_mesh = backend.tessellate(box.shape_id, deflection=0.1)
    assert len(all_verts) == len(full_mesh.vertices)


# ── STEP I/O (real OCCT) ───────────────────────────────────────────


@pytest.mark.parametrize("extension", ["step", "stp"])
def test_step_export_import_roundtrip(backend, tmp_path, extension):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput, ExportStepInput, ImportStepInput

    box = backend.create_box(CreateBoxInput(length=10.0, width=5.0, height=3.0))
    assert isinstance(box, Success) and box.shape_id

    step_path = str(tmp_path / f"test.{extension}")
    export_result = backend.export_step(ExportStepInput(shape_id=box.shape_id, filepath=step_path))
    assert isinstance(export_result, Success)

    import_result = backend.import_step(ImportStepInput(filepath=step_path))
    assert isinstance(import_result, Success)
    assert import_result.shape is not None
    # Volume should be preserved through STEP round-trip
    assert import_result.shape.volume == pytest.approx(box.shape.volume, rel=0.05)


def test_stl_export_import_roundtrip(backend, tmp_path):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput, ExportStlInput, ImportStlInput

    box = backend.create_box(CreateBoxInput(length=10.0, width=5.0, height=3.0))
    assert isinstance(box, Success) and box.shape_id

    stl_path = str(tmp_path / "test.stl")
    export_result = backend.export_stl(ExportStlInput(shape_id=box.shape_id, filepath=stl_path))
    assert isinstance(export_result, Success)

    import_result = backend.import_stl(ImportStlInput(filepath=stl_path))
    assert isinstance(import_result, Success)
    assert import_result.shape_id
    mesh = backend.tessellate(import_result.shape_id, deflection=0.1)
    assert mesh.vertices
    assert mesh.faces


# ── Native shape access ────────────────────────────────────────────


def test_get_native_shape(backend):
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.schemas import CreateBoxInput

    box = backend.create_box(CreateBoxInput(length=5.0, width=5.0, height=5.0))
    assert isinstance(box, Success) and box.shape_id

    native = backend.get_native_shape(box.shape_id)
    assert native is not None

    missing = backend.get_native_shape("nonexistent")
    assert missing is None


# ── Kernel delegation ──────────────────────────────────────────────


def test_kernel_with_occt_backend(backend):
    """Verify OpenCadKernel delegates to OcctBackend correctly."""
    from opencad_kernel.core.models import Success
    from opencad_kernel.operations.handlers import OpenCadKernel
    from opencad_kernel.operations.schemas import CreateBoxInput

    kernel = OpenCadKernel(backend=backend)
    result = kernel.create_box(CreateBoxInput(length=5.0, width=5.0, height=5.0))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume == pytest.approx(125.0, rel=0.01)

    # Tessellation should work through the kernel
    mesh = kernel.tessellate(result.shape_id, deflection=0.1)
    assert len(mesh.vertices) > 0
