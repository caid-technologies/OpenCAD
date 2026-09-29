"""Issue #93: native union contact is not an AABB overlap-volume test."""
from __future__ import annotations

import pytest

from opencad import Part, Sketch
from opencad.kernel.core.errors import ErrorCode, Failure
from opencad.kernel.operations.schemas import BooleanInput


def _box(context, *, hollow=True):
    part = Part(context=context).box(40, 30, 12)
    if hollow:
        cavity = Part(context=context).box(36, 26, 12).translate((0, 0, 2))
        part.cut(cavity)
    return part


def _post(context, *, z=6, width=1, height=1, x=18.5, y=-0.5):
    return Part(context=context).extrude(
        Sketch(context=context, origin=(0, 0, z)).rect(width, height, origin=(x, y)),
        depth=6,
    )


def _union(backend, a, b):
    return backend.boolean_union(BooleanInput(shape_a_id=a.shape_id, shape_b_id=b.shape_id))


@pytest.mark.parametrize("hollow", [False, True])
@pytest.mark.parametrize("gap", [-0.5, 0, 3e-7])
def test_union_accepts_contact_resolved_by_occt(context, backend, assert_solid, hollow, gap):
    from opencad.kernel.core.occt_backend import _bbox_from_shape

    base = _box(context, hollow=hollow)
    post = _post(context, z=6 + gap)
    sources = [backend.store.get(p.shape_id) for p in (base, post)]
    snapshots = [shape.model_dump() for shape in sources]
    native_bounds = [_bbox_from_shape(backend.get_native_shape(shape.id)) for shape in sources]
    assert [shape.bbox for shape in sources] == native_bounds
    result = _union(backend, base, post)
    expected = (5040 if hollow else 14400) + 6 + min(gap, 0)
    assert_solid(result, volume=expected)
    # Near-contact fusion must not update operand tolerances/bounds in place.
    assert [shape.model_dump() for shape in sources] == snapshots
    assert [_bbox_from_shape(backend.get_native_shape(shape.id)) for shape in sources] == native_bounds


@pytest.mark.parametrize("width,height,x,y", [(0.5, 0.5, 18.5, 0), (2, 4, 18, -2)])
def test_face_contact_does_not_depend_on_contact_area(
    context, backend, assert_solid, width, height, x, y,
):
    base = _box(context)
    post = _post(context, width=width, height=height, x=x, y=y)
    assert_solid(_union(backend, base, post), volume=5040 + width * height * 6)


@pytest.mark.parametrize("gap,code", [(5e-7, ErrorCode.BOOLEAN_KERNEL_ERROR), (0.001, ErrorCode.BBOX_NO_OVERLAP)])
def test_disjoint_posts_are_not_registered_as_success(context, backend, gap, code):
    base = _box(context)
    post = _post(context, z=6 + gap)
    before = backend.store.all_ids()
    result = _union(backend, base, post)
    assert isinstance(result, Failure)
    assert result.code == code
    assert backend.store.all_ids() == before


def test_post_floating_in_cavity_is_not_a_successful_union(context, backend):
    base = _box(context)
    # The bounding boxes overlap fully, but no material touches the shell.
    post = _post(context, x=0, y=0, z=-3)
    before_tree = context.serialize_tree()
    before_shapes = backend.store.all_ids()
    with pytest.raises(RuntimeError, match="did not join"):
        base.union(post, name="Floating post")
    assert context.serialize_tree() == before_tree
    assert backend.store.all_ids() == before_shapes


@pytest.mark.parametrize("offset", [(2, 2, 0), (2, 2, 2)])
def test_edge_or_point_contact_is_not_a_solid_join(context, backend, offset):
    a = Part(context=context).box(2, 2, 2)
    b = Part(context=context).box(2, 2, 2).translate(offset)
    result = _union(backend, a, b)
    assert isinstance(result, Failure)
    assert result.failed_check in {"boolean_result_validity", "boolean_result_connectivity"}


def test_union_preserves_existing_multisolid_patterns(context, backend, assert_solid):
    a = Part(context=context).box(2, 2, 2).linear_pattern(direction=(1, 0, 0), count=2, spacing=10)
    b = Part(context=context).box(2, 2, 2).translate((2, 0, 0))
    # Join the tool to the first patterned body; retain the other body.
    assert_solid(_union(backend, a, b), volume=24, solids=2)


def test_face_contact_remains_invalid_for_solid_intersection(context, backend):
    base = _box(context)
    post = _post(context)
    result = backend.boolean_intersection(BooleanInput(shape_a_id=base.shape_id, shape_b_id=post.shape_id))
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.BBOX_NEAR_TANGENT


def test_near_contact_union_survives_cold_rebuild_and_step_export(context, tmp_path, assert_solid):
    from opencad.kernel.core.occt_backend import OcctBackend
    from opencad.kernel.operations.schemas import ImportStepInput
    from opencad.runtime import RuntimeContext

    base = _box(context)
    base.union(_post(context, z=6 + 3e-7), name="Rim post")
    project = tmp_path / "hollow-box.json"
    context.save_tree_json(str(project))
    fresh_backend = OcctBackend()
    fresh = RuntimeContext(backend=fresh_backend)
    fresh.load_tree_json(str(project))
    node = fresh.rebuild_tree().nodes[base.feature_id]
    assert node.status == "built", node.rebuild_error
    output = tmp_path / "hollow-box.step"
    fresh.export_step(node.shape_id, str(output))
    imported_backend = OcctBackend()
    imported = imported_backend.import_step(ImportStepInput(filepath=str(output)))
    assert_solid(imported, volume=5046, owner=imported_backend)
