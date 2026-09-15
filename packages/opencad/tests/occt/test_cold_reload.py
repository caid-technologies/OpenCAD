"""Cold replay must reconstruct native shapes, not merely restore built flags."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import os
import subprocess
import sys

import pytest

from opencad import Part, Sketch
from opencad.kernel.core.occt_backend import OcctBackend
from opencad.runtime import RuntimeContext
from opencad.tree.service import FeatureTreeService


def _fresh(strategy="uuid"):
    return RuntimeContext(backend=OcctBackend(id_strategy=strategy))


def _solid(ctx, feature, volume):
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer

    node = ctx.tree.nodes[feature]
    assert node.status == "built" and node.shape_id and node.rebuild_error is None
    native = ctx.kernel.get_native_shape(node.shape_id)
    assert native is not None and not native.IsNull()
    assert BRepCheck_Analyzer(native).IsValid()
    shape = cq.Shape.cast(native)
    assert len(shape.Solids()) == 1
    assert shape.Volume() == pytest.approx(volume, rel=1e-7, abs=1e-6)
    return shape


def _save(ctx, tmp_path):
    file = tmp_path / "project.json"
    ctx.save_tree_json(str(file))
    return file


@pytest.mark.parametrize("strategy", ["uuid", "readable"])
@pytest.mark.parametrize("legacy", [False, True])
def test_cold_reload_extrude_edit_and_export(tmp_path, strategy, legacy):
    source = _fresh(strategy)
    sketch = Sketch(context=source).rect(20, 10)
    part = Part(context=source).extrude(sketch, depth=4)
    old_shape = part.shape_id
    file = _save(source, tmp_path)
    if legacy:
        payload = json.loads(file.read_text())
        payload.pop("kernel_session_id")
        for nodes in [payload["nodes"], *payload["branch_snapshots"].values()]:
            for node in nodes.values():
                node.pop("replay_shape_id", None)
                node.pop("rebuild_error", None)
        file.write_text(json.dumps(payload))
    fresh = _fresh(strategy)
    loaded = fresh.load_tree_json(str(file))
    assert loaded.nodes[loaded.root_id].status == "built"
    assert loaded.nodes[part.feature_id].status == "stale"
    assert loaded.nodes[part.feature_id].shape_id is None
    assert fresh.last_feature_id is fresh.last_shape_id is None
    assert fresh.kernel.store.all_ids() == []
    fresh.rebuild_tree()
    assert fresh.tree.nodes[part.feature_id].shape_id == old_shape
    _solid(fresh, part.feature_id, 800)
    assert fresh.last_feature_id == part.feature_id and fresh.last_shape_id == old_shape
    assert fresh.tree.nodes[part.feature_id].parameters["sketch_id"] == sketch.feature_id
    fresh.tree = FeatureTreeService.edit_feature(fresh.tree, part.feature_id, {"distance": 6})
    fresh.rebuild_tree()
    changed = _solid(fresh, part.feature_id, 1200)
    assert fresh.last_shape_id == fresh.tree.nodes[part.feature_id].shape_id != old_shape
    out = tmp_path / "after-reload.step"
    fresh.export_step(fresh.last_shape_id, str(out))
    imported = _fresh()
    feature_id, _ = imported.execute_operation("import_step", {"filepath": str(out)}, feature_name="Roundtrip")
    result = _solid(imported, feature_id, 1200)
    assert result.BoundingBox().zlen == pytest.approx(changed.BoundingBox().zlen, abs=1e-6)


@pytest.mark.parametrize("operation", ["sweep", "loft"])
def test_cold_reload_profile_features_and_repeated_edits(tmp_path, operation):
    source = _fresh()
    first = Sketch(context=source).circle(2)
    second = (Sketch(context=source, plane="XZ").line((0, 0), (0, 10)) if operation == "sweep"
              else Sketch(context=source, origin=(0, 0, 10)).circle(1))
    part = (Part(context=source).sweep(first, second) if operation == "sweep"
            else Part(context=source).loft([first, second], ruled=True))
    before = deepcopy(source.tree.nodes[part.feature_id].parameters)
    fresh = _fresh()
    fresh.load_tree_json(str(_save(source, tmp_path)))
    fresh.rebuild_tree()
    for radius in (3, 4, 2):
        segments = deepcopy(fresh.tree.nodes[first.feature_id].parameters["segments"])
        segments[0]["radius"] = radius
        fresh.tree = FeatureTreeService.edit_feature(fresh.tree, first.feature_id, {"segments": segments})
        fresh.rebuild_tree()
        expected = math.pi * 10 * (radius**2 if operation == "sweep" else (radius**2 + radius + 1) / 3)
        _solid(fresh, part.feature_id, expected)
        assert fresh.tree.nodes[part.feature_id].parameters == before


@pytest.mark.parametrize("operation", ["fillet", "chamfer", "draft", "shell"])
def test_cold_replay_preserves_saved_subshape_owners(tmp_path, operation):
    source = _fresh()
    part = Part(context=source).box(10, 10, 10)
    topology = source.get_topology(part.shape_id)
    if operation == "fillet":
        part.fillet(edges="top", radius=1)
    elif operation == "chamfer":
        part.chamfer(edges="top", distance=1)
    elif operation == "draft":
        face = max(topology.faces, key=lambda f: f.centroid[0])
        part.draft(face_ids=[face.id], angle=5)
    else:
        face = max(topology.faces, key=lambda f: f.centroid[2])
        part.shell(face_ids=[face.id], thickness=1)
    import cadquery as cq

    expected = source.kernel.store.get(part.shape_id).volume
    original = cq.Shape.cast(source.kernel.get_native_shape(part.shape_id))
    params = json.loads(json.dumps(source.tree.nodes[part.feature_id].parameters))
    fresh = _fresh()
    fresh.load_tree_json(str(_save(source, tmp_path)))
    fresh.rebuild_tree()
    restored = _solid(fresh, part.feature_id, expected)
    for axis in ("x", "y", "z"):
        assert getattr(restored.Center(), axis) == pytest.approx(getattr(original.Center(), axis), abs=1e-6)
    assert original.intersect(restored).Volume() == pytest.approx(expected, rel=1e-7, abs=1e-6)
    assert fresh.tree.nodes[part.feature_id].parameters == params
    assert fresh.tree.nodes[part.feature_id].shape_id == part.shape_id


def test_cold_reload_raw_refs_to_saved_producers(tmp_path):
    source = _fresh()
    base = Part(context=source).box(10, 10, 10)
    feature, shape = source.execute_operation(
        "translate", {"shape_id": base.shape_id, "offset": (10, 0, 0)}, feature_name="Raw reference",
        depends_on=[base.feature_id],
    )
    fresh = _fresh()
    fresh.load_tree_json(str(_save(source, tmp_path)))
    fresh.rebuild_tree()
    restored = _solid(fresh, feature, 1000)
    assert restored.Center().x == pytest.approx(10, abs=1e-6)
    assert fresh.tree.nodes[feature].shape_id == shape


def test_unknown_raw_reference_cannot_accidentally_bind_new_readable_shape(tmp_path):
    source = _fresh("readable")
    part = Part(context=source).box(10, 10, 10).translate((1, 0, 0))
    file = _save(source, tmp_path)
    payload = json.loads(file.read_text())
    payload["nodes"][part.feature_id]["parameters"]["shape_id"] = "box-0002"
    file.write_text(json.dumps(payload))
    fresh = _fresh("readable")
    before = fresh.serialize_tree()
    with pytest.raises(ValueError, match="external shape 'box-0002'"):
        fresh.load_tree_json(str(file))
    assert fresh.serialize_tree() == before and fresh.kernel.store.all_ids() == []


def test_foreign_readable_id_collision_is_atomic(tmp_path):
    source = _fresh("readable")
    Part(context=source).box(10, 10, 10)
    file = _save(source, tmp_path)
    receiver = _fresh("readable")
    unrelated = Part(context=receiver).box(2, 3, 4)
    before = receiver.serialize_tree()
    with pytest.raises(ValueError, match="collide"):
        receiver.load_tree_json(str(file))
    assert receiver.serialize_tree() == before
    _solid(receiver, unrelated.feature_id, 24)


def test_noncolliding_warm_kernel_keeps_unrelated_shapes(tmp_path):
    source = _fresh()
    part = Part(context=source).box(10, 10, 10)
    receiver = _fresh()
    unrelated = Part(context=receiver).box(2, 3, 4)
    old_native = receiver.kernel.get_native_shape(unrelated.shape_id)
    receiver.load_tree_json(str(_save(source, tmp_path)))
    receiver.rebuild_tree()
    _solid(receiver, part.feature_id, 1000)
    assert receiver.kernel.get_native_shape(unrelated.shape_id).IsSame(old_native)
    assert receiver.kernel.store.get(unrelated.shape_id).volume == pytest.approx(24)


def test_warm_reload_and_unchanged_rebuild_do_not_generate_shapes(tmp_path):
    ctx = _fresh()
    part = Part(context=ctx).box(10, 10, 10).fillet(edges="top", radius=1)
    file = _save(ctx, tmp_path)
    ids = ctx.kernel.store.all_ids()
    ctx.load_tree_json(str(file))
    assert ctx.tree.nodes[part.feature_id].status == "built"
    assert ctx.last_feature_id == part.feature_id
    for _ in range(3):
        ctx.rebuild_tree()
    assert ctx.kernel.store.all_ids() == ids


def test_native_handle_loss_is_detected_even_when_metadata_survives(tmp_path):
    ctx = _fresh()
    part = Part(context=ctx).box(10, 10, 10)
    file = _save(ctx, tmp_path)
    ctx.kernel.backend._native.pop(part.shape_id)
    assert ctx.kernel.store.get(part.shape_id) is not None
    ctx.load_tree_json(str(file))
    assert ctx.tree.nodes[part.feature_id].status == "stale"
    ctx.rebuild_tree()
    _solid(ctx, part.feature_id, 1000)


def test_suppressed_features_stay_suppressed_after_cold_load(tmp_path):
    source = _fresh()
    base = Part(context=source).box(10, 10, 10)
    base_id = base.feature_id
    base.translate((20, 0, 0))
    source.tree = FeatureTreeService.suppress_feature(source.tree, base.feature_id)
    fresh = _fresh()
    fresh.load_tree_json(str(_save(source, tmp_path)))
    fresh.rebuild_tree()
    _solid(fresh, base_id, 1000)
    assert fresh.tree.nodes[base.feature_id].status == "suppressed"
    assert fresh.tree.nodes[base.feature_id].shape_id is None
    assert fresh.last_feature_id == base_id
    fresh.tree = FeatureTreeService.suppress_feature(fresh.tree, base.feature_id, False)
    fresh.rebuild_tree()
    _solid(fresh, base.feature_id, 1000)


def test_missing_import_source_is_explicit_and_recoverable(tmp_path):
    source = _fresh()
    part = Part(context=source).box(10, 10, 10)
    step = tmp_path / "external.step"
    source.export_step(part.shape_id, str(step))
    imported = _fresh()
    fid, sid = imported.execute_operation("import_step", {"filepath": str(step)}, feature_name="Source")
    moved, _ = imported.execute_operation(
        "translate", {"shape_id": sid, "offset": (2, 0, 0)}, feature_name="Dependent",
        depends_on=[fid], tree_parameters={"shape_id": fid, "offset": (2, 0, 0)},
    )
    file = _save(imported, tmp_path)
    contents = step.read_bytes()
    step.unlink()
    fresh = _fresh()
    fresh.load_tree_json(str(file))
    fresh.rebuild_tree(continue_on_error=True)
    assert fresh.tree.nodes[fid].status == "failed"
    assert fresh.tree.nodes[fid].rebuild_error and "external.step" in fresh.tree.nodes[fid].rebuild_error
    assert fresh.tree.nodes[moved].status == "stale"
    assert fresh.tree.nodes[moved].shape_id is None
    assert fresh.kernel.store.all_ids() == []
    assert fresh.last_feature_id is fresh.last_shape_id is None
    step.write_bytes(contents)
    fresh.rebuild_tree()
    _solid(fresh, moved, 1000)
    assert all(n.rebuild_error is None for n in fresh.tree.nodes.values())


def test_save_before_rebuilding_retains_replay_plan(tmp_path):
    source = _fresh()
    part = Part(context=source).box(10, 10, 10).chamfer(edges="top", distance=1)
    volume = source.kernel.store.get(part.shape_id).volume
    file = _save(source, tmp_path)
    middle = _fresh()
    middle.load_tree_json(str(file))
    middle.save_tree_json(str(file))
    fresh = _fresh()
    fresh.load_tree_json(str(file))
    fresh.rebuild_tree()
    _solid(fresh, part.feature_id, volume)


def test_inactive_snapshots_replay_and_counters_reserve_all_branches(tmp_path):
    source = _fresh("readable")
    base = Part(context=source).box(10, 10, 10)
    source.tree = FeatureTreeService.create_branch(source.tree, "alternate")
    source.tree = FeatureTreeService.switch_branch(source.tree, "alternate")
    alternate = Part(context=source).box(2, 3, 4)
    alt_sketch = Sketch(context=source).circle(2)
    alt_sketch.build()
    source.tree = FeatureTreeService.switch_branch(source.tree, "main")
    file = _save(source, tmp_path)
    fresh = _fresh("readable")
    fresh.load_tree_json(str(file))
    assert fresh.tree.branch_snapshots["alternate"][alternate.feature_id].status == "stale"
    fresh.rebuild_tree()
    _solid(fresh, base.feature_id, 1000)
    new = Part(context=fresh).box(5, 5, 5)
    sketch = Sketch(context=fresh).circle(3)
    sketch.build()
    assert new.feature_id != alternate.feature_id
    assert sketch.feature_id != alt_sketch.feature_id
    assert new.shape_id != alternate.shape_id
    fresh.tree = FeatureTreeService.switch_branch(fresh.tree, "alternate")
    fresh.rebuild_tree()
    _solid(fresh, alternate.feature_id, 24)
    _solid(fresh, base.feature_id, 1000)
    before = fresh.kernel.store.all_ids()
    fresh.tree = FeatureTreeService.switch_branch(fresh.tree, "main")
    fresh.rebuild_tree()
    _solid(fresh, new.feature_id, 125)
    assert fresh.kernel.store.all_ids() == before


def test_cold_load_rebuilds_in_a_fresh_python_process(tmp_path):
    source = _fresh()
    part = Part(context=source).extrude(Sketch(context=source).rect(20, 10), depth=4)
    file = _save(source, tmp_path)
    out = tmp_path / "fresh-process.step"
    script = '''
import sys
import cadquery as cq
from opencad.kernel.core.occt_backend import OcctBackend
from opencad.runtime import RuntimeContext
ctx = RuntimeContext(backend=OcctBackend())
assert ctx.kernel.store.all_ids() == []
ctx.load_tree_json(sys.argv[1])
node = ctx.rebuild_tree().nodes[sys.argv[2]]
assert node.status == "built", node.rebuild_error
shape = cq.Shape.cast(ctx.kernel.get_native_shape(node.shape_id))
assert shape.isValid() and len(shape.Solids()) == 1
assert abs(shape.Volume() - 800) < 1e-6
ctx.export_step(node.shape_id, sys.argv[3])
print("cold replay exported", flush=True)
'''
    env = dict(os.environ, PYTHONFAULTHANDLER="1")
    result = subprocess.run([sys.executable, "-c", script, str(file), part.feature_id, str(out)],
                            capture_output=True, text=True, timeout=90, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "cold replay exported" in result.stdout and out.exists()
    check = _fresh()
    fid, _ = check.execute_operation("import_step", {"filepath": str(out)}, feature_name="Read child result")
    _solid(check, fid, 800)


def test_cold_reload_boolean_and_downstream_translation(tmp_path):
    source = _fresh()
    plate = Part(context=source).box(20, 10, 4)
    hole = Part(context=source).cylinder(2, 10)
    plate.cut(hole).translate((30, -5, 2))
    expected = source.kernel.store.get(plate.shape_id).volume
    fresh = _fresh()
    fresh.load_tree_json(str(_save(source, tmp_path)))
    fresh.rebuild_tree()
    shape = _solid(fresh, plate.feature_id, expected)
    assert shape.Center().x == pytest.approx(30, abs=1e-6)
    assert shape.Center().y == pytest.approx(-5, abs=1e-6)


@pytest.mark.parametrize("continue_on_error", [False, True])
def test_failed_cold_branch_never_appears_built_and_independent_work_is_optional(tmp_path, continue_on_error):
    source = _fresh()
    bad = Part(context=source).box(2, 3, 4)
    first_id = bad.feature_id
    bad.translate((10, 0, 0))
    good = Part(context=source).box(5, 5, 5)
    source.tree = FeatureTreeService.edit_feature(source.tree, first_id, {"length": -1})
    fresh = _fresh()
    fresh.load_tree_json(str(_save(source, tmp_path)))
    fresh.rebuild_tree(continue_on_error=continue_on_error)
    assert fresh.tree.nodes[first_id].status == "failed"
    assert fresh.tree.nodes[first_id].rebuild_error
    assert fresh.tree.nodes[bad.feature_id].status == "stale"
    assert fresh.tree.nodes[bad.feature_id].shape_id is None
    if continue_on_error:
        _solid(fresh, good.feature_id, 125)
    else:
        assert fresh.tree.nodes[good.feature_id].status == "stale"


def test_cold_reload_after_direct_tree_deserialization(tmp_path):
    source = _fresh()
    part = Part(context=source).box(2, 3, 4)
    fresh = _fresh()
    fresh.tree = FeatureTreeService.deserialize(source.serialize_tree())
    fresh.rebuild_tree()
    _solid(fresh, part.feature_id, 24)
    assert fresh.last_feature_id == part.feature_id
