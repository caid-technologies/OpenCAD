"""Whole-edge top selection contracts, including actual material removal.

The selector is world-Z based, not a fixed edge count, face order, or the
current camera/workplane. All tests run on fresh native geometry.
"""
from __future__ import annotations

import json
import math

import pytest


def _native(backend, shape_id):
    import cadquery as cq

    return cq.Shape.cast(backend.get_native_shape(shape_id))


def _selected_native_edges(part, backend):
    from opencad.kernel.core.occt_backend import _edge_by_index
    import cadquery as cq

    topology = backend.get_topology(part.shape_id)
    selected = set(part._resolve_edge_ids("top"))
    native = backend.get_native_shape(part.shape_id)
    return [cq.Shape.cast(_edge_by_index(native, edge.index))
            for edge in topology.edges if edge.id in selected]


@pytest.mark.parametrize("offset", [(0, 0, 0), (23, -19, 41), (0, 0, -42), (1e6, -1e6, 1e6)])
@pytest.mark.parametrize("dimensions", [(10, 8, 6), (0.1, 0.08, 0.06)])
def test_top_box_rim_uses_absolute_world_coordinates(context, backend, offset, dimensions):
    from opencad import Part

    part = Part(context=context).box(*dimensions).translate(offset)
    edges = _selected_native_edges(part, backend)
    assert len(edges) == 4
    top_z = offset[2] + dimensions[2] / 2
    for edge in edges:
        assert edge.Length() > 0
        assert all(abs(vertex.Z - top_z) < 1e-6 for vertex in edge.Vertices())
    lengths = sorted(edge.Length() for edge in edges)
    assert lengths == pytest.approx(sorted([dimensions[0], dimensions[0], dimensions[1], dimensions[1]]), abs=1e-6)


@pytest.mark.parametrize("operation", ["fillet", "chamfer"])
@pytest.mark.parametrize("offset", [(0, 0, 0), (12, -8, 37)])
def test_top_finishing_removes_only_upper_rim_material(context, backend, operation, offset, monkeypatch):
    from opencad import Part

    part = Part(context=context).box(10, 10, 10).translate(offset)
    original = _native(backend, part.shape_id)
    original_id = part.shape_id
    topology = context.get_topology(part.shape_id)
    expected_ids = {edge.id for edge in topology.edges if abs(edge.centroid[2] - (offset[2] + 5)) < 1e-6}
    assert len(expected_ids) == 4
    # This used to select arbitrary first entries. Reorder transport metadata
    # without changing the backend's IDs or native edge identity.
    topology.edges.reverse()
    monkeypatch.setattr(context, "get_topology", lambda shape_id: topology)
    assert set(part._resolve_edge_ids("top")) == expected_ids
    getattr(part, operation)(edges="top", **({"radius": 1} if operation == "fillet" else {"distance": 1}))
    finished = _native(backend, part.shape_id)
    assert finished.isValid() and len(finished.Solids()) == 1
    assert 0 < finished.Volume() < original.Volume()
    assert _native(backend, original_id).Volume() == pytest.approx(1000, abs=1e-6)
    assert set(context.tree.nodes[part.feature_id].parameters["edge_ids"]) == expected_ids

    def point(x, y, z):
        return tuple(value + delta for value, delta in zip((x, y, z), offset))

    for x, y in [(4.9, 0), (-4.9, 0), (0, 4.9), (0, -4.9)]:
        assert original.isInside(point(x, y, 4.9))
        assert not finished.isInside(point(x, y, 4.9)), "upper rim was not removed"
        assert finished.isInside(point(x, y, -4.9)), "bottom rim was incorrectly removed"
    for x in (-4.9, 4.9):
        for y in (-4.9, 4.9):
            assert finished.isInside(point(x, y, 0)), "vertical edge was incorrectly finished"
    assert finished.isInside(point(0, 0, 4.9))


@pytest.mark.parametrize("kind,count", [("cylinder", 1), ("cone", 1), ("holed_plate", 6), ("pattern", 12), ("step", 4)])
def test_top_supports_curved_rims_holes_patterns_and_steps(context, backend, kind, count):
    from opencad import Part, Sketch

    if kind == "cylinder":
        part = Part(context=context).cylinder(3, 10)
    elif kind == "cone":
        part = Part(context=context).cone(4, 2, 10)
    elif kind == "holed_plate":
        sketch = Sketch(context=context).rect(20, 10).circle(1, center=(5, 5), subtract=True).circle(1, center=(15, 5), subtract=True)
        part = Part(context=context).extrude(sketch, depth=4)
    elif kind == "pattern":
        part = Part(context=context).box(4, 4, 4).linear_pattern(direction=(1, 0, 0), count=3, spacing=10)
    else:
        part = Part(context=context).box(20, 20, 4)
        part.union(Part(context=context).box(10, 10, 2).translate((0, 0, 3)))
    edges = _selected_native_edges(part, backend)
    assert len(edges) == count
    top_z = _native(backend, part.shape_id).BoundingBox().zmax
    for edge in edges:
        assert abs(edge.BoundingBox().zmin - top_z) < 1e-6
        assert abs(edge.BoundingBox().zmax - top_z) < 1e-6
    if kind in {"cone", "cylinder"}:
        assert edges[0].geomType() == "CIRCLE", "a vertical seam is not a top rim"


@pytest.mark.parametrize("operation", ["fillet", "chamfer"])
def test_top_cylinder_finishing_keeps_bottom_rim(context, backend, operation):
    from opencad import Part

    part = Part(context=context).cylinder(3, 10).translate((12, -7, 25))
    before = _native(backend, part.shape_id)
    top_z, bottom_z = before.BoundingBox().zmax, before.BoundingBox().zmin
    getattr(part, operation)(edges="top", **({"radius": 0.5} if operation == "fillet" else {"distance": 0.5}))
    after = _native(backend, part.shape_id)
    assert after.isValid() and len(after.Solids()) == 1
    assert after.Volume() < before.Volume()
    for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
        xy = (12 + 2.95 * math.cos(angle), -7 + 2.95 * math.sin(angle))
        assert not after.isInside((*xy, top_z - 0.05))
        assert after.isInside((*xy, bottom_z + 0.05))


def test_top_does_not_promote_lower_steps_at_large_world_offset(context, backend):
    from opencad import Part

    part = Part(context=context).box(20, 20, 4)
    # A relative coordinate comparison would mistake the lower shelf at
    # Z=1000002 for the upper rim only 0.001 higher.
    part.union(Part(context=context).box(10, 10, 0.002).translate((0, 0, 2)))
    part.translate((0, 0, 1e6))
    edges = _selected_native_edges(part, backend)
    assert len(edges) == 4
    assert all(abs(v.Z - 1000002.001) < 1e-6 for edge in edges for v in edge.Vertices())


@pytest.mark.parametrize("kind", ["sphere", "torus", "apex_cone"])
@pytest.mark.parametrize("operation", ["fillet", "chamfer"])
def test_top_rejects_shapes_without_a_nondegenerate_upper_rim(context, backend, kind, operation):
    from opencad import Part

    part = Part(context=context)
    if kind == "sphere":
        part.sphere(4)
    elif kind == "torus":
        part.torus(5, 1)
    else:
        part.cone(4, 0, 10)
    before_ids = backend.store.all_ids()
    before_tree = context.serialize_tree()
    before_part = (part.shape_id, part.feature_id)
    with pytest.raises(ValueError, match="No geometric top edges"):
        getattr(part, operation)(edges="top", **({"radius": 0.5} if operation == "fillet" else {"distance": 0.5}))
    assert backend.store.all_ids() == before_ids
    assert context.serialize_tree() == before_tree
    assert (part.shape_id, part.feature_id) == before_part


def test_top_checks_whole_edges_even_when_centroids_are_misleading(context, backend, monkeypatch):
    from opencad import Part
    from opencad.kernel.core import occt_backend

    part = Part(context=context).box(10, 10, 10)
    expected = set(part._resolve_edge_ids("top"))
    assert len(expected) == 4
    # Force every edge through the cheap centroid prefilter. Only whole-edge
    # bounds may establish the tag, so the seams/vertical edges stay excluded.
    monkeypatch.setattr(occt_backend, "_edge_centroid", lambda edge: (0, 0, 5))
    assert set(part._resolve_edge_ids("top")) == expected


def test_top_curved_edge_with_high_endpoints_is_not_a_horizontal_rim(backend):
    import cadquery as cq

    edge = cq.Edge.makeSpline([cq.Vector(-4, 0, 3), cq.Vector(0, 0, 0), cq.Vector(4, 0, 3)])
    shape = backend._register_shape("wire", edge.wrapped, {})
    assert all(abs(vertex.Z - 3) < 1e-6 for vertex in edge.Vertices())
    assert edge.BoundingBox().zmin < 1
    assert not any("top" in ref.tags for ref in backend.get_topology(shape.id).edges)


def test_top_geometry_is_independent_of_coarse_tessellation(context, backend):
    from opencad import Part

    part = Part(context=context).cylinder(3, 10)
    expected = part._resolve_edge_ids("top")
    assert len(expected) == 1
    backend.tessellate(part.shape_id, deflection=2.0)
    assert part._resolve_edge_ids("top") == expected


def test_top_step_roundtrip(context, backend, registry, tmp_path):
    from opencad import Part
    from opencad.kernel.core.models import Success

    part = Part(context=context).box(10, 8, 6).translate((3, -5, 17))
    path = tmp_path / "translated.step"
    part.export_step(str(path))
    imported = registry.call("import_step", {"filepath": str(path)})
    assert isinstance(imported, Success)
    topology = backend.get_topology(imported.shape_id)
    top = [ref for ref in topology.edges if "top" in ref.tags]
    assert len(top) == 4 and all(abs(ref.centroid[2] - 20) < 1e-6 for ref in top)
    result = registry.call("chamfer_edges", {"shape_id": imported.shape_id, "edge_ids": [ref.id for ref in top], "distance": 0.5})
    assert isinstance(result, Success)
    assert _native(backend, result.shape_id).isValid()


@pytest.mark.parametrize("operation", ["fillet", "chamfer"])
def test_top_uses_serialized_topology_from_the_owning_kernel(backend, registry, operation):
    from opencad import Part
    from opencad.kernel.client import LocalKernelClient
    from opencad.runtime import RuntimeContext

    class JsonClient(LocalKernelClient):
        def get_topology(self, shape_id):
            return json.loads(json.dumps(super().get_topology(shape_id)))

    remote = RuntimeContext(kernel_client=JsonClient(registry))
    part = Part(context=remote).box(10, 10, 10).translate((0, 0, 30))
    assert remote.kernel.store.all_ids() == []
    assert len(part._resolve_edge_ids("top")) == 4
    getattr(part, operation)(edges="top", **({"radius": 1} if operation == "fillet" else {"distance": 1}))
    after = _native(backend, part.shape_id)
    assert after.isValid() and after.Volume() < 1000
    assert not after.isInside((4.9, 0, 34.9))
    assert after.isInside((4.9, 0, 25.1))
    assert remote.kernel.store.all_ids() == []


def test_top_missing_tags_never_falls_back_to_enumeration(context, backend, monkeypatch):
    from opencad import Part

    part = Part(context=context).box(10, 10, 10)
    topology = backend.get_topology(part.shape_id)
    for edge in topology.edges:
        edge.tags.clear()
    monkeypatch.setattr(context, "get_topology", lambda shape_id: topology)
    with pytest.raises(ValueError, match="No geometric top edges"):
        part._resolve_edge_ids("top")


@pytest.mark.parametrize("selector", [None, "all", "explicit"])
def test_top_fix_preserves_existing_all_and_explicit_selectors(context, backend, selector):
    from opencad import Part

    part = Part(context=context).box(10, 10, 10)
    all_ids = [edge.id for edge in backend.get_topology(part.shape_id).edges]
    spec = [all_ids[-1], all_ids[0]] if selector == "explicit" else selector
    assert part._resolve_edge_ids(spec) == (spec if isinstance(spec, list) else all_ids)


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
@pytest.mark.parametrize("depth", [-4, 4])
def test_top_is_world_z_not_the_sketch_plane_normal(context, backend, plane, depth):
    from opencad import Part, Sketch

    part = Part(context=context).extrude(Sketch(context=context, plane=plane, origin=(7, 8, 9)).rect(20, 10), depth=depth)
    top_z = _native(backend, part.shape_id).BoundingBox().zmax
    edges = _selected_native_edges(part, backend)
    assert len(edges) == 4
    assert all(abs(v.Z - top_z) < 1e-6 for edge in edges for v in edge.Vertices())


def test_top_tilted_cylinder_has_no_horizontal_upper_rim(context, backend, tmp_path):
    import cadquery as cq
    from opencad import Part

    cylinder = cq.Workplane("XY").circle(3).extrude(10).rotate((0, 0, 0), (1, 0, 0), 30)
    path = tmp_path / "tilted.step"
    cq.exporters.export(cylinder, str(path))
    part = Part(context=context)._apply("import_step", {"filepath": str(path)}, feature_name="Import tilted cylinder")
    assert _native(backend, part.shape_id).isValid()
    with pytest.raises(ValueError, match="highest world-Z plane"):
        part._resolve_edge_ids("top")
