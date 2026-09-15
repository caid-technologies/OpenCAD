"""Loft edits must resolve every section in its saved order, using current shapes."""
from __future__ import annotations

from copy import deepcopy
import math

import pytest

from opencad import Part, Sketch
from opencad.kernel_adapter import execute_feature_node
from opencad.tree.graph import MissingDependencyError
from opencad.tree.service import FeatureTreeService


def _loft(context, *, sections=((0, 2), (10, 1)), reverse=False,
          solid=True, ruled=True, plane="XY", origin=(0, 0, 0)):
    axis = {"XY": 2, "XZ": 1, "YZ": 0}[plane]
    profiles = []
    for distance, radius in sections:
        location = list(origin)
        location[axis] += distance
        profiles.append(Sketch(context=context, plane=plane, origin=tuple(location)).circle(radius))
    # Creation order deliberately differs from spatial order. Sorting feature
    # IDs or iterating the DAG instead of the saved list would be incorrect.
    for profile in reversed(profiles):
        profile.build()
    if reverse:
        profiles.reverse()
    part = Part(context=context).loft(profiles, solid=solid, ruled=ruled)
    assert all(p.feature_id != p.shape_id for p in profiles)
    assert set(context.tree.nodes[part.feature_id].depends_on) == {p.feature_id for p in profiles}
    return profiles, part.feature_id


def _edit_radius(context, profile, radius):
    segments = deepcopy(context.tree.nodes[profile.feature_id].parameters["segments"])
    segments[0]["radius"] = radius
    context.tree = FeatureTreeService.edit_feature(context.tree, profile.feature_id, {"segments": segments})


def _frustum_volume(context, profiles):
    # Independent analytic oracle for coaxial circular sections joined by ruled
    # surfaces; no kernel volume or result bounds are used to compute it.
    params = [context.tree.nodes[p.feature_id].parameters for p in profiles]
    return sum(
        math.pi * math.dist(a["origin"], b["origin"]) / 3 * (
            a["segments"][0]["radius"] ** 2
            + a["segments"][0]["radius"] * b["segments"][0]["radius"]
            + b["segments"][0]["radius"] ** 2
        )
        for a, b in zip(params, params[1:])
    )


def _shape(context, feature_id, *, volume=None, solids=1):
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer

    node = context.tree.nodes[feature_id]
    assert node.status == "built" and node.shape_id
    native = context.kernel.get_native_shape(node.shape_id)
    assert native is not None and not native.IsNull()
    assert BRepCheck_Analyzer(native).IsValid()
    shape = cq.Shape.cast(native)
    assert len(shape.Solids()) == solids
    if volume is not None:
        assert shape.Volume() == pytest.approx(volume, rel=1e-7, abs=1e-6)
    return shape


def _assert_references(context, loft_id, profiles, *, solid=True, ruled=True):
    expected = {"profile_ids": [p.feature_id for p in profiles], "solid": solid, "ruled": ruled}
    assert context.tree.nodes[loft_id].parameters == expected
    restored = FeatureTreeService.deserialize(context.serialize_tree())
    assert restored.nodes[loft_id].parameters == expected
    meta = context.kernel.store.get(context.tree.nodes[loft_id].shape_id)
    assert meta.source_ids == [context.tree.nodes[p.feature_id].shape_id for p in profiles]


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("radius", [0.5, 3])
@pytest.mark.parametrize("ruled", [False, True])
def test_loft_edit_either_section_uses_current_geometry(context, index, radius, ruled):
    profiles, loft_id = _loft(context, ruled=ruled)
    old_id = context.tree.nodes[loft_id].shape_id
    old = _shape(context, loft_id, volume=70 * math.pi / 3)
    other_id = profiles[1 - index].shape_id
    _edit_radius(context, profiles[index], radius)
    assert context.tree.nodes[loft_id].status == "stale"
    assert context.tree.nodes[loft_id].shape_id is None
    context.rebuild_tree()
    shape = _shape(context, loft_id, volume=_frustum_volume(context, profiles))
    radii = [radius, 1] if index == 0 else [2, radius]
    assert shape.BoundingBox().xlen == pytest.approx(2 * max(radii), abs=1e-6)
    assert shape.BoundingBox().zlen == pytest.approx(10, abs=1e-6)
    assert context.tree.nodes[loft_id].shape_id != old_id
    assert context.tree.nodes[profiles[1 - index].feature_id].shape_id == other_id
    assert old.Volume() == pytest.approx(70 * math.pi / 3, rel=1e-7)
    _assert_references(context, loft_id, profiles, ruled=ruled)


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("reverse", [False, True])
def test_loft_three_sections_keep_declared_order_after_edits(context, index, reverse):
    profiles, loft_id = _loft(context, sections=((0, 2), (5, 3), (12, 1)), reverse=reverse)
    _shape(context, loft_id, volume=_frustum_volume(context, profiles))
    _edit_radius(context, profiles[index], 4)
    context.rebuild_tree()
    shape = _shape(context, loft_id, volume=_frustum_volume(context, profiles))
    assert shape.BoundingBox().zmin == pytest.approx(0, abs=1e-6)
    assert shape.BoundingBox().zmax == pytest.approx(12, abs=1e-6)
    assert shape.BoundingBox().xlen == pytest.approx(8, abs=1e-6)
    _assert_references(context, loft_id, profiles)


def test_loft_repeated_edits_update_dependents_without_rebuilding_unrelated_shapes(context):
    profiles, loft_id = _loft(context)
    moved = Part(context=context)
    moved.feature_id, moved.shape_id = loft_id, context.tree.nodes[loft_id].shape_id
    moved.translate((20, -5, 0))
    unrelated = Part(context=context).box(4, 5, 6)
    for first, last, height in [(3, 1, 10), (3, 4, 15), (1, 2, 8)]:
        _edit_radius(context, profiles[0], first)
        _edit_radius(context, profiles[1], last)
        context.tree = FeatureTreeService.edit_feature(
            context.tree, profiles[1].feature_id, {"origin": (0, 0, height)},
        )
        assert context.tree.nodes[moved.feature_id].shape_id is None
        context.rebuild_tree()
        expected = _frustum_volume(context, profiles)
        _shape(context, loft_id, volume=expected)
        shape = _shape(context, moved.feature_id, volume=expected)
        assert shape.Center().x == pytest.approx(20, abs=1e-6)
        assert shape.Center().y == pytest.approx(-5, abs=1e-6)
        assert shape.BoundingBox().zlen == pytest.approx(height, abs=1e-6)
        _assert_references(context, loft_id, profiles)
        assert context.tree.nodes[moved.feature_id].parameters["shape_id"] == loft_id
        assert context.tree.nodes[unrelated.feature_id].shape_id == unrelated.shape_id
        before = context.kernel.store.all_ids()
        context.rebuild_tree()
        assert context.kernel.store.all_ids() == before


def test_loft_saved_profile_list_survives_same_kernel_json_roundtrip(context, tmp_path):
    profiles, loft_id = _loft(context, sections=((0, 2), (5, 3), (12, 1)))
    filename = tmp_path / "loft.json"
    context.save_tree_json(str(filename))
    context.load_tree_json(str(filename))  # Same kernel, NOT cold rehydration (#110).
    for index, radius in [(1, 4), (0, 1), (2, 2)]:
        _edit_radius(context, profiles[index], radius)
        context.rebuild_tree()
        _shape(context, loft_id, volume=_frustum_volume(context, profiles))
        _assert_references(context, loft_id, profiles)


@pytest.mark.parametrize("ruled", [False, True])
def test_loft_rebuild_preserves_open_shell_mode(context, ruled):
    profiles, loft_id = _loft(context, solid=False, ruled=ruled)
    _edit_radius(context, profiles[0], 3)
    context.rebuild_tree()
    shape = _shape(context, loft_id, solids=0)
    assert len(shape.Shells()) == 1
    assert shape.Area() == pytest.approx(math.pi * 4 * math.sqrt(104), rel=1e-7)
    _assert_references(context, loft_id, profiles, solid=False, ruled=ruled)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_loft_bad_reference_at_any_position_fails_then_recovers(context, index):
    profiles, loft_id = _loft(context, sections=((0, 2), (5, 3), (12, 1)))
    original = deepcopy(context.tree.nodes[loft_id].parameters)
    expected = _frustum_volume(context, profiles)
    old = _shape(context, loft_id, volume=expected)
    bad_refs = list(original["profile_ids"])
    bad_refs[index] = "missing-section"
    context.tree = FeatureTreeService.edit_feature(context.tree, loft_id, {"profile_ids": bad_refs})
    before = context.kernel.store.all_ids()
    with pytest.raises(RuntimeError, match="missing-section"):
        execute_feature_node(context.registry, context.tree.nodes[loft_id], context.tree)
    context.rebuild_tree()
    assert context.tree.nodes[loft_id].status == "failed"
    assert context.tree.nodes[loft_id].shape_id is None
    assert context.kernel.store.all_ids() == before
    assert old.Volume() == pytest.approx(expected, rel=1e-7)
    context.tree = FeatureTreeService.edit_feature(context.tree, loft_id, original)
    context.rebuild_tree()
    _shape(context, loft_id, volume=expected)
    _assert_references(context, loft_id, profiles)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_loft_stale_section_cannot_supply_cached_native_geometry(context, index):
    profiles, loft_id = _loft(context, sections=((0, 2), (5, 3), (12, 1)))
    tree = context.tree.model_copy(deep=True)
    tree.nodes[profiles[index].feature_id].status = "stale"  # Keep the old native ID on purpose.
    before = context.kernel.store.all_ids()
    with pytest.raises(ValueError, match=rf"profile_ids\[{index}\].*stale"):
        execute_feature_node(context.registry, tree.nodes[loft_id], tree)
    assert context.kernel.store.all_ids() == before
    _shape(context, loft_id, volume=_frustum_volume(context, profiles))


@pytest.mark.parametrize("index", [0, 1, 2])
def test_loft_suppressed_section_blocks_until_unsuppression(context, index):
    profiles, loft_id = _loft(context, sections=((0, 2), (5, 3), (12, 1)))
    source_id = profiles[index].feature_id
    context.tree = FeatureTreeService.suppress_feature(context.tree, source_id)
    before = context.kernel.store.all_ids()
    context.rebuild_tree()
    assert context.tree.nodes[loft_id].status != "built"
    assert context.tree.nodes[loft_id].shape_id is None
    assert context.kernel.store.all_ids() == before
    context.tree = FeatureTreeService.suppress_feature(context.tree, source_id, False)
    context.rebuild_tree()
    _shape(context, loft_id, volume=_frustum_volume(context, profiles))
    _assert_references(context, loft_id, profiles)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_loft_failed_section_build_blocks_old_loft_and_can_recover(context, index):
    profiles, loft_id = _loft(context, sections=((0, 2), (5, 3), (12, 1)))
    source_id = profiles[index].feature_id
    params = deepcopy(context.tree.nodes[source_id].parameters)
    context.tree = FeatureTreeService.edit_feature(context.tree, source_id, {"segments": []})
    before = context.kernel.store.all_ids()
    context.rebuild_tree(continue_on_error=True)
    assert context.tree.nodes[source_id].status == "failed"
    assert context.tree.nodes[loft_id].status == "stale"
    assert context.tree.nodes[loft_id].shape_id is None
    assert context.kernel.store.all_ids() == before
    context.tree = FeatureTreeService.edit_feature(context.tree, source_id, params)
    context.rebuild_tree()
    _shape(context, loft_id, volume=_frustum_volume(context, profiles))
    _assert_references(context, loft_id, profiles)


def test_loft_missing_graph_dependency_is_explicit(context):
    profiles, loft_id = _loft(context)
    tree = context.tree.model_copy(deep=True)
    del tree.nodes[profiles[0].feature_id]
    before = context.kernel.store.all_ids()
    with pytest.raises(MissingDependencyError, match=profiles[0].feature_id):
        FeatureTreeService.rebuild(tree, context._kernel_client_from_tree)
    assert context.kernel.store.all_ids() == before
    _shape(context, loft_id, volume=_frustum_volume(context, profiles))


def test_loft_missing_native_section_does_not_publish_geometry(context):
    from opencad.kernel.core.occt_backend import OcctBackend
    from opencad.runtime import RuntimeContext

    _, loft_id = _loft(context)
    empty = RuntimeContext(backend=OcctBackend(id_strategy="uuid"))
    with pytest.raises(RuntimeError, match="not found"):
        execute_feature_node(empty.registry, context.tree.nodes[loft_id], context.tree)
    assert empty.kernel.store.all_ids() == []


def test_loft_mixed_literal_and_feature_references_remain_supported(context):
    profiles, loft_id = _loft(context)
    _edit_radius(context, profiles[0], 3)
    context.rebuild_tree()
    node = context.tree.nodes[loft_id].model_copy(deep=True)
    node.parameters["profile_ids"] = [profiles[0].feature_id, profiles[1].shape_id]
    before = deepcopy(node.parameters)
    result_id = execute_feature_node(context.registry, node, context.tree)
    meta = context.kernel.store.get(result_id)
    assert meta.volume == pytest.approx(130 * math.pi / 3, rel=1e-7)
    assert meta.source_ids == [context.tree.nodes[profiles[0].feature_id].shape_id, profiles[1].shape_id]
    assert node.parameters == before


@pytest.mark.parametrize(("plane", "axis"), [("XY", "z"), ("XZ", "y"), ("YZ", "x")])
def test_loft_rebuild_respects_translated_non_z_sections(context, plane, axis):
    profiles, loft_id = _loft(context, plane=plane, origin=(20, -7, 30))
    _edit_radius(context, profiles[1], 3)
    context.rebuild_tree()
    shape = _shape(context, loft_id, volume=_frustum_volume(context, profiles))
    assert getattr(shape.BoundingBox(), f"{axis}len") == pytest.approx(10, abs=1e-6)
    _assert_references(context, loft_id, profiles)


def test_loft_rebuilt_step_roundtrip_exports_latest_three_section_geometry(context, tmp_path):
    from opencad.kernel.core.occt_backend import OcctBackend
    from opencad.runtime import RuntimeContext

    profiles, loft_id = _loft(context, sections=((0, 2), (5, 3), (12, 1)))
    _edit_radius(context, profiles[1], 4)
    context.rebuild_tree()
    expected = _frustum_volume(context, profiles)
    shape = _shape(context, loft_id, volume=expected)
    filename = tmp_path / "rebuilt-loft.step"
    context.export_step(context.tree.nodes[loft_id].shape_id, str(filename))
    fresh = RuntimeContext(backend=OcctBackend(id_strategy="uuid"))
    imported_id, _ = fresh.execute_operation("import_step", {"filepath": str(filename)}, feature_name="Imported loft")
    restored = _shape(fresh, imported_id, volume=expected)
    for name in ("xlen", "ylen", "zlen"):
        assert getattr(restored.BoundingBox(), name) == pytest.approx(getattr(shape.BoundingBox(), name), abs=1e-6)
