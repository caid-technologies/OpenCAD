"""Sweep edits must use the current native profile AND path, not cached IDs."""
from __future__ import annotations

from copy import deepcopy
import math

import pytest

from opencad import Part, Sketch
from opencad.kernel_adapter import execute_feature_node
from opencad.tree.graph import MissingDependencyError
from opencad.tree.service import FeatureTreeService


def _sweep(context, *, plane="XY", path_plane="XZ", end=(0, 10), origin=(0, 0, 0)):
    profile = Sketch(context=context, plane=plane, origin=origin).circle(2)
    path = Sketch(context=context, plane=path_plane, origin=origin).line((0, 0), end)
    part = Part(context=context).sweep(profile, path)
    assert profile.feature_id != profile.shape_id
    assert path.feature_id != path.shape_id
    assert set(context.tree.nodes[part.feature_id].depends_on) == {profile.feature_id, path.feature_id}
    return profile, path, part


def _edit_segment(context, sketch, **changes):
    segments = deepcopy(context.tree.nodes[sketch.feature_id].parameters["segments"])
    segments[0].update(changes)
    context.tree = FeatureTreeService.edit_feature(context.tree, sketch.feature_id, {"segments": segments})


def _solid(context, feature_id, *, volume):
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer

    node = context.tree.nodes[feature_id]
    assert node.status == "built" and node.shape_id
    native = context.kernel.get_native_shape(node.shape_id)
    assert native is not None and not native.IsNull()
    assert BRepCheck_Analyzer(native).IsValid()
    solid = cq.Shape.cast(native)
    assert len(solid.Solids()) == 1
    assert solid.Volume() == pytest.approx(volume, rel=1e-7, abs=1e-6)
    return solid


def _assert_references(context, part, profile, path):
    expected = {"profile_id": profile.feature_id, "path_id": path.feature_id}
    assert context.tree.nodes[part.feature_id].parameters == expected
    restored = FeatureTreeService.deserialize(context.serialize_tree())
    assert restored.nodes[part.feature_id].parameters == expected
    node = context.tree.nodes[part.feature_id]
    meta = context.kernel.store.get(node.shape_id)
    assert meta.source_ids == [context.tree.nodes[s.feature_id].shape_id for s in (profile, path)]


@pytest.mark.parametrize("radius", [0.5, 3, 5])
def test_sweep_profile_edit_rebuilds_material_and_preserves_sources(context, radius):
    profile, path, part = _sweep(context)
    old = _solid(context, part.feature_id, volume=40 * math.pi)
    old_id = part.shape_id
    _edit_segment(context, profile, radius=radius)
    assert context.tree.nodes[part.feature_id].status == "stale"
    assert context.tree.nodes[part.feature_id].shape_id is None
    context.rebuild_tree()
    new = _solid(context, part.feature_id, volume=radius**2 * 10 * math.pi)
    assert new.BoundingBox().xlen == pytest.approx(2 * radius, abs=1e-6)
    assert new.BoundingBox().zlen == pytest.approx(10, abs=1e-6)
    assert context.tree.nodes[part.feature_id].shape_id != old_id
    assert old.Volume() == pytest.approx(40 * math.pi, rel=1e-7)
    assert context.kernel.get_native_shape(old_id) is not None
    _assert_references(context, part, profile, path)


@pytest.mark.parametrize("length", [5, 15, 25])
def test_sweep_path_edit_invalidates_sweep_and_uses_new_length(context, length):
    profile, path, part = _sweep(context)
    original_profile_id = profile.shape_id
    _edit_segment(context, path, end=(0, length))
    assert context.tree.nodes[part.feature_id].status == "stale"
    context.rebuild_tree()
    solid = _solid(context, part.feature_id, volume=4 * length * math.pi)
    assert solid.BoundingBox().zmin == pytest.approx(0, abs=1e-6)
    assert solid.BoundingBox().zmax == pytest.approx(length, abs=1e-6)
    assert context.tree.nodes[profile.feature_id].shape_id == original_profile_id
    _assert_references(context, part, profile, path)


@pytest.mark.parametrize(("plane", "path_plane", "axis", "end"), [
    ("XY", "XZ", "z", (0, 15)),
    ("YZ", "XY", "x", (15, 0)),
    ("XZ", "XY", "y", (0, 15)),
])
def test_sweep_rebuild_is_not_tied_to_world_z_or_origin(context, plane, path_plane, axis, end):
    profile, path, part = _sweep(context, plane=plane, path_plane=path_plane,
                                 end=(end[0] * 2 / 3, end[1] * 2 / 3), origin=(20, -7, 30))
    _edit_segment(context, profile, radius=3)
    _edit_segment(context, path, end=end)
    context.rebuild_tree()
    solid = _solid(context, part.feature_id, volume=135 * math.pi)
    assert getattr(solid.BoundingBox(), f"{axis}len") == pytest.approx(15, abs=1e-6)
    _assert_references(context, part, profile, path)


def test_sweep_repeated_edits_rebuild_dependents_but_not_unrelated_shapes(context):
    profile, path, part = _sweep(context)
    sweep_id = part.feature_id
    part.translate((20, 0, 0))
    translated_id = part.feature_id
    unrelated = Part(context=context).box(4, 5, 6)
    old_unrelated = unrelated.shape_id
    for radius, length in [(3, 10), (3, 15), (1, 6), (2, 10)]:
        _edit_segment(context, profile, radius=radius)
        _edit_segment(context, path, end=(0, length))
        assert context.tree.nodes[translated_id].shape_id is None
        assert context.tree.nodes[unrelated.feature_id].shape_id == old_unrelated
        context.rebuild_tree()
        _solid(context, sweep_id, volume=math.pi * radius**2 * length)
        moved = _solid(context, translated_id, volume=math.pi * radius**2 * length)
        assert moved.Center().x == pytest.approx(20, abs=1e-6)
        assert context.tree.nodes[sweep_id].parameters == {
            "profile_id": profile.feature_id, "path_id": path.feature_id,
        }
        assert context.tree.nodes[translated_id].parameters["shape_id"] == sweep_id
        assert context.tree.nodes[unrelated.feature_id].shape_id == old_unrelated
        ids_before = context.kernel.store.all_ids()
        context.rebuild_tree()
        assert context.kernel.store.all_ids() == ids_before, "unchanged rebuild must not create geometry"


def test_sweep_saved_references_survive_serialization_in_owning_kernel(context, tmp_path):
    profile, path, part = _sweep(context)
    filename = tmp_path / "sweep.json"
    context.save_tree_json(str(filename))
    context.load_tree_json(str(filename))  # Same owning kernel; not cold rehydration (#110).
    _edit_segment(context, profile, radius=3)
    context.rebuild_tree()
    _solid(context, part.feature_id, volume=90 * math.pi)
    _assert_references(context, part, profile, path)
    _edit_segment(context, path, end=(0, 20))
    context.rebuild_tree()
    _solid(context, part.feature_id, volume=180 * math.pi)
    _assert_references(context, part, profile, path)


@pytest.mark.parametrize("key", ["profile_id", "path_id"])
def test_sweep_bad_reference_fails_without_publishing_then_recovers(context, key):
    profile, path, part = _sweep(context)
    parameters = deepcopy(context.tree.nodes[part.feature_id].parameters)
    old = _solid(context, part.feature_id, volume=40 * math.pi)
    context.tree = FeatureTreeService.edit_feature(context.tree, part.feature_id, {key: "missing-shape"})
    before = context.kernel.store.all_ids()
    with pytest.raises(RuntimeError, match="missing-shape"):
        execute_feature_node(context.registry, context.tree.nodes[part.feature_id], context.tree)
    context.rebuild_tree()
    assert context.tree.nodes[part.feature_id].status == "failed"
    assert context.tree.nodes[part.feature_id].shape_id is None
    assert context.kernel.store.all_ids() == before
    assert old.Volume() == pytest.approx(40 * math.pi, rel=1e-7)
    context.tree = FeatureTreeService.edit_feature(context.tree, part.feature_id, parameters)
    context.rebuild_tree()
    _solid(context, part.feature_id, volume=40 * math.pi)
    _assert_references(context, part, profile, path)


@pytest.mark.parametrize("which", ["profile", "path"])
def test_sweep_suppressed_input_blocks_then_unsuppression_recovers(context, which):
    profile, path, part = _sweep(context)
    source = profile if which == "profile" else path
    context.tree = FeatureTreeService.suppress_feature(context.tree, source.feature_id)
    before = context.kernel.store.all_ids()
    context.rebuild_tree()
    assert context.tree.nodes[part.feature_id].status != "built"
    assert context.tree.nodes[part.feature_id].shape_id is None
    assert context.kernel.store.all_ids() == before
    context.tree = FeatureTreeService.suppress_feature(context.tree, source.feature_id, False)
    context.rebuild_tree()
    _solid(context, part.feature_id, volume=40 * math.pi)
    _assert_references(context, part, profile, path)


@pytest.mark.parametrize("which", ["profile", "path"])
def test_sweep_missing_feature_dependency_is_explicit(context, which):
    profile, path, part = _sweep(context)
    source = profile if which == "profile" else path
    broken = context.tree.model_copy(deep=True)
    del broken.nodes[source.feature_id]  # Simulate a damaged/imported tree.
    before = context.kernel.store.all_ids()
    with pytest.raises(MissingDependencyError, match=source.feature_id):
        FeatureTreeService.rebuild(broken, context._kernel_client_from_tree)
    assert context.kernel.store.all_ids() == before
    _solid(context, part.feature_id, volume=40 * math.pi)


def test_sweep_missing_native_geometry_is_not_replaced_by_cached_success(context):
    from opencad.kernel.core.occt_backend import OcctBackend
    from opencad.runtime import RuntimeContext

    _, _, part = _sweep(context)
    empty = RuntimeContext(backend=OcctBackend(id_strategy="uuid"))
    node = context.tree.nodes[part.feature_id]
    with pytest.raises(RuntimeError, match="not found"):
        execute_feature_node(empty.registry, node, context.tree)
    assert empty.kernel.store.all_ids() == []


def test_sweep_raw_native_ids_remain_supported(context):
    profile, path, part = _sweep(context)
    node = context.tree.nodes[part.feature_id].model_copy(deep=True)
    node.parameters = {"profile_id": profile.shape_id, "path_id": path.shape_id}
    shape_id = execute_feature_node(context.registry, node, context.tree)
    assert shape_id != part.shape_id
    assert context.kernel.store.get(shape_id).volume == pytest.approx(40 * math.pi, rel=1e-7)
    assert node.parameters == {"profile_id": profile.shape_id, "path_id": path.shape_id}


def test_sweep_rebuilt_step_roundtrip_uses_latest_geometry(context, tmp_path):
    from opencad.kernel.core.occt_backend import OcctBackend
    from opencad.runtime import RuntimeContext

    profile, path, part = _sweep(context)
    _edit_segment(context, profile, radius=3)
    _edit_segment(context, path, end=(0, 15))
    context.rebuild_tree()
    solid = _solid(context, part.feature_id, volume=135 * math.pi)
    filename = tmp_path / "rebuilt-sweep.step"
    context.export_step(context.tree.nodes[part.feature_id].shape_id, str(filename))
    fresh = RuntimeContext(backend=OcctBackend(id_strategy="uuid"))
    imported_id, _ = fresh.execute_operation(
        "import_step", {"filepath": str(filename)}, feature_name="Imported sweep",
    )
    restored = _solid(fresh, imported_id, volume=135 * math.pi)
    for name in ("xlen", "ylen", "zlen"):
        assert getattr(restored.BoundingBox(), name) == pytest.approx(getattr(solid.BoundingBox(), name), abs=1e-6)


@pytest.mark.parametrize("which", ["profile", "path"])
def test_sweep_failed_input_build_blocks_cached_geometry_then_recovers(context, which):
    profile, path, part = _sweep(context)
    source = profile if which == "profile" else path
    params = deepcopy(context.tree.nodes[source.feature_id].parameters)
    old_sweep = _solid(context, part.feature_id, volume=40 * math.pi)
    context.tree = FeatureTreeService.edit_feature(context.tree, source.feature_id, {"segments": []})
    before = context.kernel.store.all_ids()
    context.rebuild_tree(continue_on_error=True)
    assert context.tree.nodes[source.feature_id].status == "failed"
    assert context.tree.nodes[part.feature_id].status == "stale"
    assert context.tree.nodes[part.feature_id].shape_id is None
    assert context.kernel.store.all_ids() == before
    assert old_sweep.Volume() == pytest.approx(40 * math.pi, rel=1e-7)
    context.tree = FeatureTreeService.edit_feature(context.tree, source.feature_id, params)
    context.rebuild_tree()
    _solid(context, part.feature_id, volume=40 * math.pi)
    _assert_references(context, part, profile, path)


@pytest.mark.parametrize("which", ["profile", "path"])
def test_sweep_stale_feature_with_existing_native_shape_cannot_be_used(context, which):
    profile, path, part = _sweep(context)
    source = profile if which == "profile" else path
    assert context.kernel.get_native_shape(source.shape_id) is not None
    tree = context.tree.model_copy(deep=True)
    tree.nodes[source.feature_id].status = "stale"  # Deliberately retain its old native ID.
    before = context.kernel.store.all_ids()
    with pytest.raises(ValueError, match=rf"{source.feature_id}.*stale"):
        execute_feature_node(context.registry, tree.nodes[part.feature_id], tree)
    assert context.kernel.store.all_ids() == before
    _solid(context, part.feature_id, volume=40 * math.pi)
