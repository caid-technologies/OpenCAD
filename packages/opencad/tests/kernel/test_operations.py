from __future__ import annotations

import json

import pytest

from opencad.kernel.core.errors import ErrorCode, Failure
from opencad.kernel.core.models import BoundingBox, Success
from opencad.kernel.operations.handlers import OpenCadKernel
from opencad.kernel.operations.registry import OperationRegistry
from opencad.kernel.operations.schemas import (
    BooleanInput,
    CreateBoxInput,
    CreateCylinderInput,
    CreateSphereInput,
    ExportStlInput,
    ExportStepInput,
    FilletEdgesInput,
    ImportStlInput,
    ImportStepInput,
    OffsetShapeInput,
    TranslateInput,
)


@pytest.fixture()
def kernel() -> OpenCadKernel:
    return OpenCadKernel(tolerance=1e-6, id_strategy="readable")


@pytest.fixture()
def registry(kernel: OpenCadKernel) -> OperationRegistry:
    return OperationRegistry(kernel)


def _translate_shape(kernel: OpenCadKernel, shape_id: str, dx: float, dy: float, dz: float) -> None:
    shape = kernel.store.get(shape_id)
    assert shape is not None
    shape.bbox = BoundingBox(
        min_x=shape.bbox.min_x + dx,
        min_y=shape.bbox.min_y + dy,
        min_z=shape.bbox.min_z + dz,
        max_x=shape.bbox.max_x + dx,
        max_y=shape.bbox.max_y + dy,
        max_z=shape.bbox.max_z + dz,
    )
    kernel.store.add(shape)


def _make_two_boxes(kernel: OpenCadKernel) -> tuple[str, str]:
    a = kernel.create_box(CreateBoxInput(length=1.0, width=1.0, height=1.0))
    b = kernel.create_box(CreateBoxInput(length=1.0, width=1.0, height=1.0))
    assert isinstance(a, Success) and isinstance(b, Success)
    assert a.shape_id and b.shape_id
    return a.shape_id, b.shape_id


def test_create_box_success(kernel: OpenCadKernel) -> None:
    result = kernel.create_box(CreateBoxInput(length=2.0, width=3.0, height=4.0))
    assert isinstance(result, Success)
    assert result.ok
    assert result.shape is not None
    assert result.shape.volume == pytest.approx(24.0)


def test_create_cylinder_success(kernel: OpenCadKernel) -> None:
    result = kernel.create_cylinder(CreateCylinderInput(radius=2.0, height=3.0))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > 0.0


def test_create_sphere_success(kernel: OpenCadKernel) -> None:
    result = kernel.create_sphere(CreateSphereInput(radius=2.5))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > 0.0


def test_translate_moves_bbox_without_changing_volume(kernel: OpenCadKernel) -> None:
    box = kernel.create_box(CreateBoxInput(length=2.0, width=3.0, height=4.0))
    assert isinstance(box, Success) and box.shape is not None and box.shape_id

    result = kernel.translate(TranslateInput(shape_id=box.shape_id, offset=(10.0, -2.0, 5.0)))

    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.kind == "translate"
    assert result.shape.volume == pytest.approx(box.shape.volume)
    assert result.shape.bbox.min_x == pytest.approx(10.0)
    assert result.shape.bbox.min_y == pytest.approx(-2.0)
    assert result.shape.bbox.min_z == pytest.approx(5.0)
    assert result.shape.bbox.max_x == pytest.approx(12.0)
    assert result.shape.bbox.max_y == pytest.approx(1.0)
    assert result.shape.bbox.max_z == pytest.approx(9.0)


def test_create_box_invalid_input(kernel: OpenCadKernel) -> None:
    result = kernel.create_box(CreateBoxInput(length=-1.0, width=2.0, height=3.0))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.INVALID_INPUT


def test_boolean_union_success(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    result = kernel.boolean_union(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > 0.0


def test_boolean_union_bounds_bbox_overlap_by_operand_volume(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    shape_a = kernel.store.get(a_id)
    shape_b = kernel.store.get(b_id)
    assert shape_a is not None and shape_b is not None
    shape_a.volume = 0.2
    shape_b.volume = 0.3
    kernel.store.add(shape_a)
    kernel.store.add(shape_b)

    result = kernel.boolean_union(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))

    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume == pytest.approx(0.3)


def test_boolean_union_no_overlap_fails(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    _translate_shape(kernel, b_id, dx=10.0, dy=0.0, dz=0.0)
    result = kernel.boolean_union(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.BBOX_NO_OVERLAP


def test_boolean_intersection_success(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    _translate_shape(kernel, b_id, dx=0.2, dy=0.0, dz=0.0)
    result = kernel.boolean_intersection(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > 0.0


def test_boolean_intersection_near_tangent_fails(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    _translate_shape(kernel, b_id, dx=0.9999999, dy=0.0, dz=0.0)
    result = kernel.boolean_intersection(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.BBOX_NEAR_TANGENT


def test_boolean_cut_success(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    _translate_shape(kernel, b_id, dx=0.5, dy=0.0, dz=0.0)
    result = kernel.boolean_cut(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > 0.0


def test_boolean_cut_zero_volume_fails(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    result = kernel.boolean_cut(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.ZERO_VOLUME


def test_boolean_union_non_manifold_fails(kernel: OpenCadKernel) -> None:
    a_id, b_id = _make_two_boxes(kernel)
    kernel.store.set_manifold(b_id, False)
    result = kernel.boolean_union(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.NON_MANIFOLD


def test_boolean_shape_not_found_fails(kernel: OpenCadKernel) -> None:
    result = kernel.boolean_union(BooleanInput(shape_a_id="missing", shape_b_id="also-missing"))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.SHAPE_NOT_FOUND


def test_fillet_success(kernel: OpenCadKernel) -> None:
    box = kernel.create_box(CreateBoxInput(length=5.0, width=5.0, height=5.0))
    assert isinstance(box, Success) and box.shape is not None and box.shape_id
    edge_id = box.shape.edge_ids[0]
    result = kernel.fillet_edges(FilletEdgesInput(shape_id=box.shape_id, edge_ids=[edge_id], radius=0.5))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume < box.shape.volume


def test_fillet_radius_too_large_fails(kernel: OpenCadKernel) -> None:
    box = kernel.create_box(CreateBoxInput(length=2.0, width=2.0, height=2.0))
    assert isinstance(box, Success) and box.shape is not None and box.shape_id
    result = kernel.fillet_edges(
        FilletEdgesInput(shape_id=box.shape_id, edge_ids=[box.shape.edge_ids[0]], radius=1.0)
    )
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.FILLET_RADIUS_TOO_LARGE


def test_fillet_requires_edges(kernel: OpenCadKernel) -> None:
    box = kernel.create_box(CreateBoxInput(length=2.0, width=2.0, height=2.0))
    assert isinstance(box, Success) and box.shape_id
    result = kernel.fillet_edges(FilletEdgesInput(shape_id=box.shape_id, edge_ids=[], radius=0.1))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.INVALID_INPUT


def test_offset_positive_success(kernel: OpenCadKernel) -> None:
    box = kernel.create_box(CreateBoxInput(length=1.0, width=1.0, height=1.0))
    assert isinstance(box, Success) and box.shape is not None and box.shape_id
    result = kernel.offset_shape(OffsetShapeInput(shape_id=box.shape_id, distance=0.25))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume > box.shape.volume


def test_offset_negative_collapse_fails(kernel: OpenCadKernel) -> None:
    box = kernel.create_box(CreateBoxInput(length=1.0, width=1.0, height=1.0))
    assert isinstance(box, Success) and box.shape_id
    result = kernel.offset_shape(OffsetShapeInput(shape_id=box.shape_id, distance=-0.6))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.OFFSET_COLLAPSE


def test_import_step_success(kernel: OpenCadKernel, tmp_path) -> None:
    step_file = tmp_path / "part.step"
    payload = {
        "volume": 42.0,
        "bbox": {
            "min_x": 0,
            "min_y": 0,
            "min_z": 0,
            "max_x": 3,
            "max_y": 2,
            "max_z": 7,
        },
    }
    step_file.write_text(f"OPENCAD-MOCK\n{json.dumps(payload)}\n", encoding="utf-8")
    result = kernel.import_step(ImportStepInput(filepath=str(step_file)))
    assert isinstance(result, Success)
    assert result.shape is not None
    assert result.shape.volume == pytest.approx(42.0)


def test_import_step_missing_file_fails(kernel: OpenCadKernel, tmp_path) -> None:
    missing = tmp_path / "missing.step"
    result = kernel.import_step(ImportStepInput(filepath=str(missing)))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.IO_ERROR


def test_analytic_export_step_is_rejected(kernel: OpenCadKernel, tmp_path) -> None:
    sphere = kernel.create_sphere(CreateSphereInput(radius=2.0))
    assert isinstance(sphere, Success) and sphere.shape_id
    out_path = tmp_path / "out.step"
    result = kernel.export_step(ExportStepInput(shape_id=sphere.shape_id, filepath=str(out_path)))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.UNSUPPORTED_STEP
    assert not out_path.exists()


def test_export_step_missing_shape_fails(kernel: OpenCadKernel, tmp_path) -> None:
    out_path = tmp_path / "out.step"
    result = kernel.export_step(ExportStepInput(shape_id="missing", filepath=str(out_path)))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.SHAPE_NOT_FOUND


def test_stl_export_import_roundtrip(kernel: OpenCadKernel, tmp_path) -> None:
    box = kernel.create_box(CreateBoxInput(length=4.0, width=3.0, height=2.0))
    assert isinstance(box, Success) and box.shape_id

    stl_path = tmp_path / "box.stl"
    export_result = kernel.export_stl(ExportStlInput(shape_id=box.shape_id, filepath=str(stl_path)))
    assert isinstance(export_result, Success)
    assert stl_path.read_text(encoding="utf-8").startswith("solid opencad")

    import_result = kernel.import_stl(ImportStlInput(filepath=str(stl_path)))
    assert isinstance(import_result, Success)
    assert import_result.shape is not None
    assert import_result.shape.bbox == box.shape.bbox


def test_export_stl_missing_shape_fails(kernel: OpenCadKernel, tmp_path) -> None:
    result = kernel.export_stl(
        ExportStlInput(shape_id="missing", filepath=str(tmp_path / "missing.stl"))
    )
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.SHAPE_NOT_FOUND


def test_registry_has_all_10_operations(registry: OperationRegistry) -> None:
    ops = registry.list_operations()
    assert len(ops) >= 10
    assert {
        "create_box",
        "create_cylinder",
        "create_sphere",
        "boolean_union",
        "boolean_cut",
        "boolean_intersection",
        "fillet_edges",
        "offset_shape",
        "import_step",
        "export_step",
        "import_stl",
        "export_stl",
        "translate",
    }.issubset(set(ops))


def test_registry_exposes_json_schema(registry: OperationRegistry) -> None:
    schema = registry.get_json_schema("create_box")
    assert "properties" in schema
    assert "length" in schema["properties"]


def test_operations_return_structured_failure(registry: OperationRegistry) -> None:
    result = registry.call("create_box", {"length": -1.0, "width": 1.0, "height": 1.0})
    assert isinstance(result, Failure)
    assert result.ok is False
    assert result.code == ErrorCode.INVALID_INPUT


def test_boolean_kernel_exception_is_caught(kernel: OpenCadKernel, monkeypatch) -> None:
    a_id, b_id = _make_two_boxes(kernel)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(kernel.backend, "_run_boolean", _boom)
    result = kernel.boolean_union(BooleanInput(shape_a_id=a_id, shape_b_id=b_id))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.BOOLEAN_KERNEL_ERROR


def test_registry_unknown_operation_returns_failure(registry: OperationRegistry) -> None:
    result = registry.call("missing_op", {})
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.INVALID_INPUT
    assert result.failed_check == "operation_lookup"


def test_registry_invalid_payload_returns_failure(registry: OperationRegistry) -> None:
    result = registry.call("create_box", {"length": 1.0, "width": 2.0})
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.INVALID_INPUT
    assert result.failed_check == "schema_validation"


def test_registry_unknown_schema_raises_value_error(registry: OperationRegistry) -> None:
    with pytest.raises(ValueError, match="Unknown operation"):
        registry.get_json_schema("missing_op")
