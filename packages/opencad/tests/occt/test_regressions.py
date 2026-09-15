"""Audit regressions: draft/top/sweep repaired; two known cases remain.

Each xfail is strict: a repaired feature produces XPASS and fails until the
marker is removed. --strict-regressions runs all of these as ordinary failures.
Only the final defect assertion is inside xfail scope: setup errors must fail.
"""
from __future__ import annotations

import math

import pytest


def _known_defect(request, reason):
    # Apply after setup/control assertions; an unrelated setup failure stays red.
    request.node.add_marker(pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason))


def test_draft_uses_a_neutral_plane(registry, backend, assert_solid):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    assert_solid(box, volume=1000)
    side = max(backend.get_topology(box.shape_id).faces, key=lambda face: face.centroid[0])
    result = registry.call("draft", {"shape_id": box.shape_id, "face_ids": [side.id], "angle": 5})
    shape = assert_solid(result)
    assert shape.BoundingBox().xlen != pytest.approx(10, abs=1e-5)
    slope = math.tan(math.radians(5))
    assert shape.Volume() == pytest.approx(1000, rel=1e-7)
    for z in (-5, 5):
        rim = [v.X for v in shape.Vertices() if abs(v.Z - z) < 1e-6]
        assert max(rim) == pytest.approx(5 - z * slope, abs=1e-6)


def test_top_selector_is_geometric(context, backend):
    from opencad import Part

    part = Part(context=context).box(10, 10, 10)
    topology = backend.get_topology(part.shape_id)
    expected = {edge.id for edge in topology.edges if abs(edge.centroid[2] - 5) < 1e-6}
    assert len(expected) == 4, "control geometry must have four top edges"
    selected = set(part._resolve_edge_ids("top"))
    assert selected == expected


@pytest.mark.parametrize("operation", ["sweep", "loft"])
def test_profile_references_survive_rebuild(request, context, backend, operation):
    import cadquery as cq
    from opencad import Part, Sketch
    from opencad.tree.service import FeatureTreeService

    first = Sketch(context=context).circle(2)
    second = (Sketch(context=context, plane="XZ").line((0, 0), (0, 10))
              if operation == "sweep" else Sketch(context=context, origin=(0, 0, 10)).circle(1))
    part = (Part(context=context).sweep(first, second) if operation == "sweep"
            else Part(context=context).loft([first, second], ruled=True))
    original = cq.Shape.cast(backend.get_native_shape(part.shape_id))
    assert original.isValid() and original.Volume() > 0
    # Change the section radius through the actual stored sketch segments.
    params = context.tree.nodes[first.feature_id].parameters
    segments = [dict(segment) for segment in params["segments"]]
    segments[0]["radius"] = 3
    context.tree = FeatureTreeService.edit_feature(context.tree, first.feature_id, {"segments": segments})
    rebuilt = context.rebuild_tree().nodes[part.feature_id]
    if operation == "loft":
        _known_defect(request, "OCCT-003-loft: profile list references are not resolved on rebuild")
    assert rebuilt.status == "built", f"{operation} rebuild status: {rebuilt.status}"
    native = backend.get_native_shape(rebuilt.shape_id)
    assert native is not None
    shape = cq.Shape.cast(native)
    assert shape.isValid() and len(shape.Solids()) == 1
    expected = 90 * math.pi if operation == "sweep" else 130 * math.pi / 3
    assert shape.Volume() == pytest.approx(expected, rel=1e-7)


def test_saved_tree_rehydrates_an_empty_kernel(request, context, tmp_path):
    import cadquery as cq
    from opencad import Part, Sketch
    from opencad.kernel.core.occt_backend import OcctBackend
    from opencad.runtime import RuntimeContext

    part = Part(context=context).extrude(Sketch(context=context).rect(20, 10), depth=4)
    path = tmp_path / "tree.json"
    context.save_tree_json(str(path))
    fresh = RuntimeContext(backend=OcctBackend())
    assert fresh.kernel.store.all_ids() == []
    fresh.load_tree_json(str(path))
    rebuilt = fresh.rebuild_tree().nodes[part.feature_id]
    native = fresh.kernel.get_native_shape(rebuilt.shape_id)
    _known_defect(request, "OCCT-004: loaded built nodes skip native reconstruction")
    assert native is not None, "serialized shape IDs are not native geometry"
    shape = cq.Shape.cast(native)
    assert shape.isValid() and len(shape.Solids()) == 1
    assert shape.Volume() == pytest.approx(800, rel=1e-7)
