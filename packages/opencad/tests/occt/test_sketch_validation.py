"""Issue #97: reject invalid profiles where they originate, before booleans."""
from __future__ import annotations

import math

import pytest

from opencad import Part, Sketch
from opencad.kernel.core.errors import ErrorCode, Failure


@pytest.mark.parametrize("x", [87, 90, 93, 100])
def test_invalid_subtractive_circle_fails_before_feature_creation(context, backend, x):
    # x=87 touches internally; x=90 crosses the edge (the reported example);
    # x=93 touches externally; x=100 lies completely outside the plate.
    profile = Sketch(context=context, name="Plate profile").rect(90, 40).circle(
        3, center=(x, 20), subtract=True,
    )
    before_tree = context.tree.model_dump()
    with pytest.raises(RuntimeError) as error:
        Part(context=context).extrude(profile, depth=5, name="Plate body")
    message = str(error.value)
    assert "create_sketch" in message and "Plate profile" in message
    assert "strictly inside" in message and "touch" in message
    assert "cut" in message
    assert backend.store.all_ids() == []
    assert context.tree.model_dump() == before_tree
    assert profile.shape_id is None and profile.feature_id is None


@pytest.mark.parametrize("second_x", [45, 49, 51])
def test_overlapping_or_touching_holes_are_rejected(registry, backend, rectangle, second_x):
    result = registry.call("create_sketch", {"segments": [
        *rectangle(90, 40),
        {"type": "circle", "center": (45, 20), "radius": 3, "subtract": True},
        {"type": "circle", "center": (second_x, 20), "radius": 3, "subtract": True},
    ]})
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.SKETCH_ERROR
    assert "subtractive" in result.message.lower()
    assert backend.store.all_ids() == []


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
def test_valid_holes_still_extrude_and_cut(registry, assert_solid, rectangle, plane):
    profile = registry.call("create_sketch", {"plane": plane, "origin": (7, 8, 9), "segments": [
        *rectangle(90, 40),
        {"type": "circle", "center": (45, 20), "radius": 3, "subtract": True},
        {"type": "circle", "center": (75, 20), "radius": 3, "subtract": True},
    ]})
    assert profile.ok
    plate = registry.call("extrude", {"sketch_id": profile.shape_id, "distance": 5})
    assert_solid(plate, volume=(90 * 40 - 2 * math.pi * 3**2) * 5)
    slot_profile = registry.call("create_sketch", {
        "plane": plane, "origin": (7, 8, 9), "segments": rectangle(10, 4, x=20, y=18),
    })
    slot = registry.call("extrude", {"sketch_id": slot_profile.shape_id, "distance": 5})
    result = registry.call("boolean_cut", {"shape_a_id": plate.shape_id, "shape_b_id": slot.shape_id})
    assert_solid(result, volume=(90 * 40 - 2 * math.pi * 3**2 - 10 * 4) * 5)


@pytest.mark.parametrize("points", [
    [(0, 0), (10, 0)],  # An open path is valid for a sweep, not for a solid extrusion.
    [(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)],  # Self-intersection.
])
def test_invalid_extrusion_does_not_store_a_built_solid(context, backend, points):
    profile = Sketch(context=context, name="Invalid profile")
    for start, end in zip(points, points[1:]):
        profile.line(start, end)
    profile.build()
    before_ids = backend.store.all_ids()
    before_tree = context.tree.model_dump()
    with pytest.raises(RuntimeError) as error:
        Part(context=context).extrude(profile, depth=5, name="Plate body")
    assert "Plate body" in str(error.value)
    assert "profile" in str(error.value).lower()
    assert backend.store.all_ids() == before_ids
    assert context.tree.model_dump() == before_tree


def test_documented_edge_notch_and_rectangular_slot_are_valid(context, backend):
    import cadquery as cq

    plate = Part(context=context).extrude(Sketch(context=context).rect(90, 40), depth=5)
    notch = Part(context=context).extrude(
        Sketch(context=context).circle(3, center=(90, 20)), depth=5,
    )
    plate.cut(notch)
    slot = Part(context=context).extrude(
        Sketch(context=context).rect(10, 4, origin=(20, 18)), depth=5,
    )
    plate.cut(slot)
    native = cq.Shape.cast(backend.get_native_shape(plate.shape_id))
    assert native.isValid() and len(native.Solids()) == 1
    assert native.Volume() == pytest.approx((90 * 40 - math.pi * 3**2 / 2 - 10 * 4) * 5)


def test_near_zero_volume_extrusion_is_not_registered(registry, backend, rectangle):
    profile = registry.call("create_sketch", {"segments": rectangle(0.01, 0.01)})
    assert profile.ok
    before_ids = backend.store.all_ids()
    result = registry.call("extrude", {"sketch_id": profile.shape_id, "distance": 0.001})
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.EXTRUDE_FAILURE
    assert result.failed_check == "extrude_result"
    assert backend.store.all_ids() == before_ids


def test_editing_a_hole_to_the_boundary_fails_rebuild_at_the_sketch(context):
    from opencad.tree.service import FeatureTreeService

    profile = Sketch(context=context).rect(90, 40).circle(3, center=(45, 20), subtract=True)
    plate = Part(context=context).extrude(profile, depth=5)
    segments = [dict(segment) for segment in context.tree.nodes[profile.feature_id].parameters["segments"]]
    segments[-1]["center"] = (90, 20)
    context.tree = FeatureTreeService.edit_feature(context.tree, profile.feature_id, {"segments": segments})
    rebuilt = context.rebuild_tree()
    sketch_node = rebuilt.nodes[profile.feature_id]
    assert sketch_node.status == "failed"
    assert sketch_node.shape_id is None
    assert "strictly inside" in sketch_node.rebuild_error
    assert rebuilt.nodes[plate.feature_id].status != "built"
    assert rebuilt.nodes[plate.feature_id].shape_id is None
