"""Cheap native contracts; no files, tessellation, UI, network, or LLM."""
from __future__ import annotations

import math

import pytest


@pytest.mark.parametrize("operation,payload,volume", [
    ("create_box", {"length": 10, "width": 4, "height": 2}, 80.0),
    ("create_cylinder", {"radius": 2, "height": 5}, 20 * math.pi),
    ("create_sphere", {"radius": 3}, 36 * math.pi),
    ("create_cone", {"radius1": 2, "radius2": 0.5, "height": 5}, 8.75 * math.pi),
    ("create_torus", {"major_radius": 5, "minor_radius": 1}, 10 * math.pi ** 2),
], ids=["box", "cylinder", "sphere", "cone", "torus"])
def test_primitive_native_contract(registry, assert_solid, operation, payload, volume):
    result = registry.call(operation, payload)
    assert_solid(result, volume=volume)
    entry = registry.get_log()[-1]
    assert entry.success and entry.backend == "OcctBackend"
    assert entry.result_shape_id == result.shape_id


def test_translate_preserves_volume_and_source(registry, backend, assert_solid):
    original = registry.call("create_box", {"length": 8, "width": 4, "height": 2})
    assert_solid(original, volume=64)
    original_bounds = original.shape.bbox.model_dump()
    moved = registry.call("translate", {"shape_id": original.shape_id, "offset": (12, -3, 5)})
    assert_solid(moved, volume=64)
    assert moved.shape_id != original.shape_id
    assert moved.shape.bbox.model_dump() == pytest.approx({
        "min_x": 8, "max_x": 16, "min_y": -5, "max_y": -1, "min_z": 4, "max_z": 6,
    }, abs=1e-5)
    assert backend.store.get(original.shape_id).bbox.model_dump() == original_bounds


@pytest.mark.parametrize("operation,volume", [
    ("boolean_union", 128), ("boolean_cut", 48), ("boolean_intersection", 32),
])
def test_boolean_partial_overlap(registry, backend, assert_solid, operation, volume):
    # Not coincident boxes: the old union/intersection examples could be no-ops.
    a = registry.call("create_box", {"length": 10, "width": 4, "height": 2})
    b = registry.call("create_box", {"length": 10, "width": 4, "height": 2})
    b = registry.call("translate", {"shape_id": b.shape_id, "offset": (6, 0, 0)})
    result = registry.call(operation, {"shape_a_id": a.shape_id, "shape_b_id": b.shape_id})
    assert_solid(result, volume=volume)
    assert backend.store.get(a.shape_id).volume == pytest.approx(80)
    assert backend.store.get(b.shape_id).volume == pytest.approx(80)


@pytest.mark.parametrize("operation,payload", [
    ("create_box", {"length": 0, "width": 2, "height": 3}),
    ("create_cylinder", {"radius": -1, "height": 3}),
    ("create_sphere", {"radius": 0}),
    ("create_torus", {"major_radius": 1, "minor_radius": 2}),
    ("extrude", {"sketch_id": "missing", "distance": 3}),
])
def test_invalid_input_does_not_create_shapes(registry, backend, operation, payload):
    from opencad.kernel.core.errors import Failure

    before = backend.store.all_ids()
    result = registry.call(operation, payload)
    assert isinstance(result, Failure), repr(result)
    assert backend.store.all_ids() == before
    assert not registry.get_log()[-1].success
