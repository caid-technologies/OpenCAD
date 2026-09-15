"""Native draft contracts for #106; no expected failures in this module."""
from __future__ import annotations

import math

import pytest

from opencad.kernel.core.errors import ErrorCode, Failure


def _side(backend, shape_id, axis=0):
    return max(backend.get_topology(shape_id).faces, key=lambda face: face.centroid[axis]).id


def _vertices(shape):
    return sorted(vertex.toTuple() for vertex in shape.Vertices())


def _check_rims(shape, *, neutral_z, angle=5, offset=(0, 0, 0), pull_sign=1):
    """Analytic side-plane equation, independent of OCCT's draft builder."""
    ox, oy, oz = offset
    slope = pull_sign * math.tan(math.radians(angle))
    for z in (oz - 5, oz + 5):
        rim = [vertex for vertex in shape.Vertices() if abs(vertex.Z - z) < 1e-6]
        assert len(rim) == 4
        assert min(vertex.X for vertex in rim) == pytest.approx(ox - 5, abs=1e-6)
        assert max(vertex.X for vertex in rim) == pytest.approx(ox + 5 - (z - neutral_z) * slope, abs=1e-6)
        assert sorted(vertex.Y for vertex in rim) == pytest.approx([oy - 5, oy - 5, oy + 5, oy + 5], abs=1e-6)


@pytest.mark.parametrize("angle", [-5, 5])
@pytest.mark.parametrize("neutral_z", [-5, 0, 5])
def test_draft_signed_angle_and_neutral_height(registry, backend, assert_solid, angle, neutral_z):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    source = assert_solid(box, volume=1000)
    original_vertices = _vertices(source)
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": [_side(backend, box.shape_id)],
        "angle": angle, "neutral_plane_origin": (0, 0, neutral_z),
    })
    # Average displacement of one 10x10 side is neutral_z * tan(angle).
    expected_volume = 1000 + 100 * neutral_z * math.tan(math.radians(angle))
    shape = assert_solid(result, volume=expected_volume)
    _check_rims(shape, neutral_z=neutral_z, angle=angle)
    assert _vertices(source) == original_vertices
    assert source.Volume() == pytest.approx(1000, abs=1e-6)
    assert result.shape.source_ids == [box.shape_id]


def test_draft_translated_part_and_explicit_plane(registry, backend, assert_solid):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    offset = (12, -7, 20)
    moved = registry.call("translate", {"shape_id": box.shape_id, "offset": offset})
    source = assert_solid(moved, volume=1000)
    original = _vertices(source)
    result = registry.call("draft", {
        "shape_id": moved.shape_id, "face_ids": [_side(backend, moved.shape_id)],
        "angle": 5, "pull_direction": (0, 0, 2),
        "neutral_plane_origin": (12, -7, 15), "neutral_plane_normal": (0, 0, 7),
    })
    shape = assert_solid(result, volume=1000 - 500 * math.tan(math.radians(5)))
    _check_rims(shape, offset=offset, neutral_z=15)
    assert _vertices(source) == original
    assert result.shape.parameters["neutral_plane_origin"] == (12, -7, 15)
    assert result.shape.parameters["neutral_plane_normal"] == (0, 0, 7)


def test_draft_oblique_neutral_plane_is_not_ignored(registry, backend, assert_solid):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": [_side(backend, box.shape_id)], "angle": 5,
        "neutral_plane_origin": (0, 0, -5), "neutral_plane_normal": (1, 0, 1),
    })
    # x + z = -5 intersects the original +X side (x=5) at z=-10.
    shape = assert_solid(result, volume=1000 - 1000 * math.tan(math.radians(5)))
    _check_rims(shape, neutral_z=-10)


def test_draft_reversed_pull_reverses_taper(registry, backend, assert_solid):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": [_side(backend, box.shape_id)], "angle": 5,
        "pull_direction": (0, 0, -2), "neutral_plane_origin": (0, 0, -5),
        "neutral_plane_normal": (0, 0, 1),
    })
    shape = assert_solid(result, volume=1000 + 500 * math.tan(math.radians(5)))
    _check_rims(shape, neutral_z=-5, pull_sign=-1)


@pytest.mark.parametrize("pull_axis", [0, 1])
def test_draft_default_normal_follows_non_z_pull(registry, backend, assert_solid, pull_axis):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    side_axis = (pull_axis + 1) % 3
    pull = [0.0, 0.0, 0.0]
    pull[pull_axis] = 3.0
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": [_side(backend, box.shape_id, side_axis)],
        "angle": 5, "pull_direction": pull,
    })
    shape = assert_solid(result, volume=1000)
    for coord in (-5, 5):
        rim = [v.toTuple()[side_axis] for v in shape.Vertices() if abs(v.toTuple()[pull_axis] - coord) < 1e-6]
        assert len(rim) == 4
        assert max(rim) == pytest.approx(5 - coord * math.tan(math.radians(5)), abs=1e-6)


@pytest.mark.parametrize("magnitude", [1e-300, 1e300])
def test_draft_direction_magnitude_does_not_change_geometry(registry, backend, assert_solid, magnitude):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": [_side(backend, box.shape_id)], "angle": 5,
        "pull_direction": (0, 0, magnitude), "neutral_plane_normal": (0, 0, magnitude),
    })
    _check_rims(assert_solid(result, volume=1000), neutral_z=0)


@pytest.mark.parametrize("operation,parameters", [
    ("create_cylinder", {"radius": 5, "height": 10}),
    ("create_cone", {"radius1": 5, "radius2": 3, "height": 10}),
])
def test_draft_supported_curved_side(registry, backend, assert_solid, operation, parameters):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Cone
    import cadquery as cq

    base = registry.call(operation, parameters)
    source = assert_solid(base)
    source_volume = source.Volume()
    index = next(i for i, f in enumerate(source.Faces()) if BRepAdaptor_Surface(f.wrapped).GetType() in (GeomAbs_Cylinder, GeomAbs_Cone))
    # Face references come from the same native topology enumeration.
    face_id = base.shape.face_ids[index]
    lower_z = source.BoundingBox().zmin
    result = registry.call("draft", {
        "shape_id": base.shape_id, "face_ids": [face_id], "angle": 5,
        "neutral_plane_origin": (0, 0, lower_z),
    })
    drafted = assert_solid(result)
    # OCCT's curved-face draft sets the angle relative to the pull axis (it
    # is not an additive change to an existing cone's half angle).
    top = 5 - 10 * math.tan(math.radians(5))
    expected = math.pi * 10 / 3 * (25 + 5 * top + top * top)
    assert drafted.Volume() == pytest.approx(expected, rel=1e-7)
    assert cq.Shape.cast(backend.get_native_shape(base.shape_id)).Volume() == pytest.approx(source_volume, rel=1e-9)


@pytest.mark.parametrize("changes", [
    {"angle": 0}, {"angle": 90}, {"angle": -90}, {"angle": 100},
    {"angle": float("nan")}, {"angle": float("inf")},
    {"pull_direction": (0, 0, 0)}, {"pull_direction": (0, 0, float("inf"))},
    {"neutral_plane_normal": (0, 0, 0)}, {"neutral_plane_normal": (0, float("nan"), 1)},
    {"neutral_plane_origin": (0, 0, float("inf"))},
    {"neutral_plane_origin": (0, 0)}, {"neutral_plane_normal": (0, 1)},
    {"face_ids": []}, {"face_ids": ["not-a-face"]},
])
def test_draft_invalid_input_preserves_state(registry, backend, assert_solid, changes):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    shape = assert_solid(box, volume=1000)
    vertices = _vertices(shape)
    ids = backend.store.all_ids()
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": [_side(backend, box.shape_id)], "angle": 5, **changes,
    })
    assert isinstance(result, Failure)
    assert result.code == ErrorCode.INVALID_INPUT
    assert backend.store.all_ids() == ids
    assert _vertices(shape) == vertices
    assert shape.Volume() == pytest.approx(1000, abs=1e-6)


@pytest.mark.parametrize("bad_selection", ["foreign", "out-of-range", "edge", "duplicate"])
def test_draft_rejects_wrong_face_reference(registry, backend, assert_solid, bad_selection):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    other = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    selected = {
        "foreign": [other.shape.face_ids[0]], "out-of-range": [f"{box.shape_id}:face:999"],
        "edge": [box.shape.edge_ids[0]], "duplicate": [box.shape.face_ids[0]] * 2,
    }[bad_selection]
    ids = backend.store.all_ids()
    result = registry.call("draft", {"shape_id": box.shape_id, "face_ids": selected, "angle": 5})
    assert isinstance(result, Failure) and result.code == ErrorCode.INVALID_INPUT
    assert backend.store.all_ids() == ids
    assert_solid(box, volume=1000)


@pytest.mark.parametrize("operation,payload", [
    ("create_sphere", {"radius": 5}),
    ("create_torus", {"major_radius": 5, "minor_radius": 1}),
])
def test_draft_rejects_unsupported_surface(registry, backend, operation, payload):
    base = registry.call(operation, payload)
    ids = backend.store.all_ids()
    result = registry.call("draft", {"shape_id": base.shape_id, "face_ids": [base.shape.face_ids[0]], "angle": 5})
    assert isinstance(result, Failure) and result.code == ErrorCode.INVALID_INPUT
    assert "not planar, cylindrical, or conical" in result.message
    assert backend.store.all_ids() == ids


@pytest.mark.parametrize("failure_case", ["parallel-face", "partial-selection", "collapse"])
def test_draft_kernel_failure_does_not_publish_shape(registry, backend, assert_solid, failure_case):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    source = assert_solid(box, volume=1000)
    vertices = _vertices(source)
    side, top = _side(backend, box.shape_id), _side(backend, box.shape_id, 2)
    faces = [top] if failure_case == "parallel-face" else [side, top] if failure_case == "partial-selection" else [side]
    ids = backend.store.all_ids()
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": faces,
        "angle": 89 if failure_case == "collapse" else 5, "neutral_plane_origin": (0, 0, -5),
    })
    assert isinstance(result, Failure) and result.code == ErrorCode.DRAFT_FAILURE
    assert result.failed_check == ("draft_build" if failure_case == "collapse" else "draft_add")
    assert backend.store.all_ids() == ids
    assert _vertices(source) == vertices
    assert source.Volume() == pytest.approx(1000, abs=1e-6)


def test_draft_fluent_parameters_roundtrip_and_rebuild(context, backend, tmp_path):
    import cadquery as cq
    from opencad import Part
    from opencad.tree.service import FeatureTreeService

    part = Part(context=context).box(10, 10, 10).translate((12, -7, 20))
    source_id = part.shape_id
    part.draft(face_ids=[_side(backend, source_id)], angle=5,
               pull_direction=(0, 0, 2), neutral_plane_origin=(12, -7, 15), neutral_plane_normal=(0, 0, 7))
    # Round-trip serialization in the SAME owning kernel: cold rehydration is
    # separately tracked in #110 and is deliberately not fixed in this PR.
    context.adopt_tree(FeatureTreeService.deserialize(context.serialize_tree()))
    stored = context.tree.nodes[part.feature_id].parameters
    assert stored["neutral_plane_origin"] == [12, -7, 15]
    assert stored["neutral_plane_normal"] == [0, 0, 7]
    assert stored["pull_direction"] == [0, 0, 2]
    for angle, plane_z in [(7, 15), (-4, 25), (5, 20)]:
        context.tree = FeatureTreeService.edit_feature(context.tree, part.feature_id, {
            "angle": angle, "neutral_plane_origin": [12, -7, plane_z],
        })
        node = context.rebuild_tree().nodes[part.feature_id]
        assert node.status == "built"
        shape = cq.Shape.cast(backend.get_native_shape(node.shape_id))
        assert shape.isValid() and len(shape.Solids()) == 1
        _check_rims(shape, offset=(12, -7, 20), neutral_z=plane_z, angle=angle)
        expected = 1000 + 100 * (plane_z - 20) * math.tan(math.radians(angle))
        assert shape.Volume() == pytest.approx(expected, rel=1e-7)
        assert backend.store.get(node.shape_id).parameters["neutral_plane_origin"] == (12, -7, plane_z)
    context.export_step(node.shape_id, str(tmp_path / "draft.step"))
    imported = cq.importers.importStep(str(tmp_path / "draft.step")).val()
    assert imported.isValid() and len(imported.Solids()) == 1
    assert imported.Volume() == pytest.approx(shape.Volume(), rel=1e-7)


def test_draft_schema_exposes_compatible_plane_defaults(registry):
    from opencad.kernel.operations.schemas import DraftInput

    payload = DraftInput(shape_id="source", face_ids=["source:face:0"], angle=5)
    assert payload.neutral_plane_origin == (0, 0, 0)
    assert payload.neutral_plane_normal is None
    schema = registry.get_json_schema("draft")
    assert set(schema["required"]) == {"shape_id", "face_ids", "angle"}
    assert schema["properties"]["neutral_plane_origin"]["default"] == [0, 0, 0]
    assert schema["properties"]["neutral_plane_normal"]["default"] is None


def test_draft_multiple_side_faces(registry, backend, assert_solid):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    sides = [face.id for face in backend.get_topology(box.shape_id).faces if abs(face.centroid[2]) < 1e-6]
    assert len(sides) == 4
    result = registry.call("draft", {
        "shape_id": box.shape_id, "face_ids": sides, "angle": 5,
        "neutral_plane_origin": (0, 0, -5),
    })
    width = 10 - 20 * math.tan(math.radians(5))
    shape = assert_solid(result, volume=10 / 3 * (100 + 10 * width + width * width))
    for z, half_width in [(-5, 5), (5, width / 2)]:
        rim = [v for v in shape.Vertices() if abs(v.Z - z) < 1e-6]
        assert len(rim) == 4
        for vertex in rim:
            assert abs(vertex.X) == pytest.approx(half_width, abs=1e-6)
            assert abs(vertex.Y) == pytest.approx(half_width, abs=1e-6)


def test_draft_rejects_open_shell(context, registry, backend):
    from opencad import Part, Sketch

    shell = Part(context=context).loft([
        Sketch(context=context).circle(5),
        Sketch(context=context, origin=(0, 0, 10)).circle(3),
    ], solid=False, ruled=True)
    ids = backend.store.all_ids()
    face = backend.get_topology(shell.shape_id).faces[0]
    result = registry.call("draft", {"shape_id": shell.shape_id, "face_ids": [face.id], "angle": 5})
    assert isinstance(result, Failure) and result.code == ErrorCode.INVALID_INPUT
    assert "valid solid" in result.message
    assert backend.store.all_ids() == ids


def test_draft_missing_shape(registry, backend):
    result = registry.call("draft", {"shape_id": "missing", "face_ids": ["missing:face:0"], "angle": 5})
    assert isinstance(result, Failure) and result.code == ErrorCode.SHAPE_NOT_FOUND
    assert backend.store.all_ids() == []
