"""Native geometry, feature-edit, mesh, and interchange contracts."""
from __future__ import annotations

import math

import pytest


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
@pytest.mark.parametrize("distance,both", [(4, False), (-4, False), (4, True)])
def test_extrude_signed_and_symmetric(registry, assert_solid, rectangle, plane, distance, both):
    sketch = registry.call("create_sketch", {
        "plane": plane, "origin": (3, 7, 11), "segments": rectangle(20, 10),
    })
    result = registry.call("extrude", {
        "sketch_id": sketch.shape_id, "distance": distance, "both": both,
    })
    assert_solid(result, volume=200 * abs(distance) * (2 if both else 1))
    axis, origin = {"XY": ("z", 11), "XZ": ("y", 7), "YZ": ("x", 3)}[plane]
    low, high = (getattr(result.shape.bbox, f"{bound}_{axis}") for bound in ("min", "max"))
    assert high - low == pytest.approx(abs(distance) * (2 if both else 1), abs=1e-5)
    if both:
        assert (low + high) / 2 == pytest.approx(origin, abs=1e-5)


def _plate(registry, rectangle):
    sketch = registry.call("create_sketch", {"segments": [
        *rectangle(20, 10),
        {"type": "circle", "center": (5, 5), "radius": 1, "subtract": True},
        {"type": "circle", "center": (15, 5), "radius": 1, "subtract": True},
    ]})
    return registry.call("extrude", {"sketch_id": sketch.shape_id, "distance": 4})


def test_plate_with_two_holes(registry, assert_solid, rectangle):
    assert_solid(_plate(registry, rectangle), volume=(200 - 2 * math.pi) * 4)


@pytest.mark.parametrize("operation,parameter,expected", [
    ("fillet_edges", {"radius": 1}, 1000 - 10 * (1 - math.pi / 4)),
    ("chamfer_edges", {"distance": 1}, 995),
])
def test_edge_feature_removes_expected_material(registry, assert_solid, operation, parameter, expected):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    result = registry.call(operation, {
        "shape_id": box.shape_id, "edge_ids": [box.shape.edge_ids[0]], **parameter,
    })
    assert_solid(result, volume=expected)


def test_open_top_shell(registry, backend, assert_solid):
    box = registry.call("create_box", {"length": 10, "width": 10, "height": 10})
    top = max(backend.get_topology(box.shape_id).faces, key=lambda face: face.centroid[2])
    result = registry.call("shell", {"shape_id": box.shape_id, "face_ids": [top.id], "thickness": 1})
    assert_solid(result, volume=1000 - 8 * 8 * 9)


def test_revolve_annular_profile(registry, assert_solid, rectangle):
    sketch = registry.call("create_sketch", {"plane": "XZ", "segments": rectangle(3, 4, x=2)})
    result = registry.call("revolve", {"shape_id": sketch.shape_id})
    assert_solid(result, volume=math.pi * (5 ** 2 - 2 ** 2) * 4)


def test_straight_sweep(registry, assert_solid):
    profile = registry.call("create_sketch", {
        "segments": [{"type": "circle", "center": (0, 0), "radius": 2}],
    })
    path = registry.call("create_sketch", {
        "plane": "XZ", "segments": [{"type": "line", "start": (0, 0), "end": (0, 10)}],
    })
    result = registry.call("sweep", {"profile_id": profile.shape_id, "path_id": path.shape_id})
    assert_solid(result, volume=40 * math.pi)


def test_ruled_loft(registry, assert_solid):
    profiles = [registry.call("create_sketch", {
        "origin": (0, 0, height),
        "segments": [{"type": "circle", "center": (0, 0), "radius": radius}],
    }) for height, radius in [(0, 2), (10, 1)]]
    result = registry.call("loft", {"profile_ids": [p.shape_id for p in profiles], "ruled": True})
    assert_solid(result, volume=70 * math.pi / 3)


@pytest.mark.parametrize("operation,payload,count,expected_centers", [
    ("linear_pattern", {"direction": (1, 0, 0), "count": 3, "spacing": 6}, 3,
     [(10, 0, 0), (16, 0, 0), (22, 0, 0)]),
    ("circular_pattern", {"count": 4}, 4,
     [(-10, 0, 0), (0, -10, 0), (0, 10, 0), (10, 0, 0)]),
    ("mirror", {}, 2, [(-10, 0, 0), (10, 0, 0)]),
])
def test_patterns_preserve_body_count(registry, assert_solid, operation, payload, count, expected_centers):
    seed = registry.call("create_box", {"length": 2, "width": 2, "height": 2})
    seed = registry.call("translate", {"shape_id": seed.shape_id, "offset": (10, 0, 0)})
    result = registry.call(operation, {"shape_id": seed.shape_id, **payload})
    shape = assert_solid(result, volume=8 * count, solids=count)
    centers = sorted(tuple(round(v, 6) for v in solid.Center().toTuple()) for solid in shape.Solids())
    assert centers == sorted(expected_centers)


@pytest.mark.parametrize("extension", ["step", "stp"])
def test_step_roundtrip_in_fresh_kernel(registry, assert_solid, rectangle, tmp_path, extension):
    from opencad.kernel.core.models import Success
    from opencad.kernel.core.occt_backend import OcctBackend
    from opencad.kernel.operations.schemas import ImportStepInput

    plate = _plate(registry, rectangle)
    assert_solid(plate, volume=(200 - 2 * math.pi) * 4)
    path = tmp_path / f"plate.{extension}"
    exported = registry.call("export_step", {"shape_id": plate.shape_id, "filepath": str(path)})
    assert isinstance(exported, Success), repr(exported)
    assert path.stat().st_size > 0
    restored_backend = OcctBackend()
    restored = restored_backend.import_step(ImportStepInput(filepath=str(path)))
    assert_solid(restored, volume=plate.shape.volume, owner=restored_backend)
    assert restored.shape.bbox.model_dump() == pytest.approx(plate.shape.bbox.model_dump(), abs=1e-5)


def test_mesh_indices_and_triangle_area(registry, backend, assert_solid):
    import numpy as np

    cylinder = registry.call("create_cylinder", {"radius": 2, "height": 5})
    assert_solid(cylinder, volume=20 * math.pi)
    mesh = backend.tessellate(cylinder.shape_id, deflection=0.05)
    assert len(mesh.vertices) % 3 == len(mesh.faces) % 3 == 0
    vertices = np.asarray(mesh.vertices).reshape(-1, 3)
    faces = np.asarray(mesh.faces).reshape(-1, 3)
    assert len(vertices) and len(faces)
    assert np.isfinite(vertices).all()
    assert faces.min() >= 0 and faces.max() < len(vertices)
    triangles = vertices[faces]
    doubled_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    assert (doubled_area > 1e-12).all(), "degenerate mesh triangles"
    cursor = 0
    for group in mesh.face_groups:
        assert group.start == cursor and group.count % 3 == 0
        assert group.owner_shape_id == cylinder.shape_id
        cursor += group.count
    assert cursor == len(mesh.faces)


def test_extrusion_edit_rebuilds_native_geometry(context, backend):
    import cadquery as cq
    from opencad import Part, Sketch
    from opencad.tree.service import FeatureTreeService

    part = Part(context=context).extrude(Sketch(context=context).rect(20, 10), depth=4)
    old_shape = part.shape_id
    context.tree = FeatureTreeService.edit_feature(context.tree, part.feature_id, {"distance": 7})
    rebuilt = context.rebuild_tree().nodes[part.feature_id]
    assert rebuilt.status == "built" and rebuilt.shape_id != old_shape
    shape = cq.Shape.cast(backend.get_native_shape(rebuilt.shape_id))
    assert shape.isValid() and len(shape.Solids()) == 1
    assert shape.Volume() == pytest.approx(1400, rel=1e-7)
