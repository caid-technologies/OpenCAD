"""Portable tree state and identity allocation do not require native libraries."""
from __future__ import annotations

from copy import deepcopy
import json
from unittest.mock import Mock

import pytest

from opencad import Part
from opencad.rehydration import prepare_tree
from opencad.runtime import RuntimeContext
from opencad.tree.models import FeatureNode, FeatureTree
from opencad.tree.service import FeatureTreeService


def _tree():
    return FeatureTree(root_id="root", kernel_session_id="original", nodes={
        "root": FeatureNode(id="root", name="Root", operation="seed", status="built"),
        "base": FeatureNode(id="base", name="Base", operation="create_box", status="built",
                            parameters={"length": 2, "width": 3, "height": 4}, shape_id="box-0007"),
        "moved": FeatureNode(id="moved", name="Moved", operation="translate", status="built",
                             parameters={"shape_id": "base", "offset": [1, 0, 0]},
                             depends_on=["base"], shape_id="translate-0003"),
    })


@pytest.mark.parametrize("session", [None, "original"])
def test_foreign_and_legacy_tree_metadata_do_not_certify_geometry(session):
    tree = _tree()
    tree.kernel_session_id = session
    before = tree.model_dump()
    ready = prepare_tree(tree, session_id="new", has_shape=lambda _: False, occupied_ids=set())
    assert tree.model_dump() == before
    assert ready.nodes["root"].status == "built" and ready.nodes["root"].shape_id is None
    assert ready.nodes["base"].status == ready.nodes["moved"].status == "stale"
    assert ready.nodes["base"].shape_id is ready.nodes["moved"].shape_id is None
    assert ready.nodes["base"].replay_shape_id == "box-0007"
    assert ready.nodes["moved"].parameters["shape_id"] == "base"
    assert ready.kernel_session_id == "new"


def test_owned_live_tree_is_not_invalidated():
    tree = _tree()
    ready = prepare_tree(tree, session_id="original", has_shape=lambda _: True, occupied_ids={"box-0007"})
    assert ready.nodes == tree.nodes


def test_missing_owned_geometry_invalidates_dependent_not_unrelated_nodes():
    tree = _tree()
    tree.nodes["independent"] = FeatureNode(id="independent", name="Other", operation="create_box",
                                           status="built", shape_id="box-0008")
    ready = prepare_tree(tree, session_id="original", has_shape=lambda sid: sid != "box-0007",
                         occupied_ids={"translate-0003", "box-0008"})
    assert ready.nodes["base"].replay_shape_id == "box-0007"
    assert ready.nodes["moved"].status == "stale" and ready.nodes["moved"].replay_shape_id is None
    assert ready.nodes["independent"].status == "built"


def test_shape_bearing_root_is_an_operation_not_a_seed():
    tree = _tree()
    tree.root_id = "base"
    del tree.nodes["root"]
    ready = prepare_tree(tree, session_id="new", has_shape=lambda _: False, occupied_ids=set())
    assert ready.nodes["base"].status == "stale"


@pytest.mark.parametrize("key,value", [
    ("shape_id", "external"), ("profile_ids", ["base", "external"]),
    ("edge_ids", ["external:edge:0"]), ("face_ids", ["external:face:0"]),
])
def test_unportable_references_are_explicit_and_non_mutating(key, value):
    tree = _tree()
    tree.nodes["moved"].parameters[key] = value
    before = tree.model_dump()
    with pytest.raises(ValueError, match="external"):
        prepare_tree(tree, session_id="new", has_shape=lambda _: False, occupied_ids=set())
    assert tree.model_dump() == before


def test_branch_snapshot_collision_is_checked_before_adoption():
    tree = _tree()
    tree.branch_snapshots["inactive"] = deepcopy(tree.nodes)
    tree.branch_snapshots["inactive"]["base"].shape_id = "box-0042"
    with pytest.raises(ValueError, match="box-0042"):
        prepare_tree(tree, session_id="new", has_shape=lambda _: False, occupied_ids={"box-0042"})


@pytest.mark.parametrize("bad", ["not JSON", json.dumps({"root_id": "root", "nodes": {"bad": {"no_id": True}}})])
def test_invalid_load_does_not_mutate_current_tree_or_cursors(tmp_path, bad):
    ctx = RuntimeContext()
    Part(context=ctx).box(2, 3, 4)
    before = ctx.serialize_tree(), ctx.last_feature_id, ctx.last_shape_id, ctx.kernel.store.all_ids()
    file = tmp_path / "bad.json"
    file.write_text(bad)
    with pytest.raises(ValueError):
        ctx.load_tree_json(str(file))
    assert (ctx.serialize_tree(), ctx.last_feature_id, ctx.last_shape_id, ctx.kernel.store.all_ids()) == before


def test_external_runtime_does_not_silently_replay_in_the_local_kernel(tmp_path):
    owner = RuntimeContext()
    Part(context=owner).box(2, 3, 4)
    file = tmp_path / "tree.json"
    owner.save_tree_json(str(file))
    client = Mock()
    remote = RuntimeContext(kernel_client=client)
    before = remote.serialize_tree()
    with pytest.raises(NotImplementedError, match="owning in-process kernel"):
        remote.load_tree_json(str(file))
    assert remote.serialize_tree() == before
    client.call_operation.assert_not_called()
    assert remote.kernel.store.all_ids() == []


def test_analytic_cold_reload_does_not_require_occt(tmp_path):
    source = RuntimeContext()
    part = Part(context=source).box(2, 3, 4)
    file = tmp_path / "tree.json"
    source.save_tree_json(str(file))
    fresh = RuntimeContext()
    fresh.load_tree_json(str(file))
    fresh.rebuild_tree()
    node = fresh.tree.nodes[part.feature_id]
    assert node.status == "built" and node.replay_shape_id is None
    assert fresh.kernel.store.get(node.shape_id).volume == 24
    next_part = Part(context=fresh).box(1, 1, 1)
    assert next_part.shape_id != node.shape_id and next_part.feature_id != part.feature_id


def test_readable_allocation_avoids_replay_reservations_and_existing_ids():
    from opencad.kernel.operations.handlers import OpenCadKernel
    from opencad.kernel.operations.registry import OperationRegistry

    kernel = OpenCadKernel(id_strategy="readable")
    registry = OperationRegistry(kernel)
    kernel.store.reserve_ids({"box-0001", "box-0003"})
    args = {"length": 2, "width": 3, "height": 4}
    assert registry.call("create_box", args).shape_id == "box-0002"
    assert registry.call("create_box", args, replay_shape_id="box-0001").shape_id == "box-0001"
    assert registry.call("create_box", args).shape_id == "box-0004"
    assert registry.call("create_box", args, replay_shape_id="box-0003").shape_id == "box-0003"
    with pytest.raises(ValueError, match="Duplicate"):
        kernel.store.new_id("box", preset_id="box-0001")
    assert len(kernel.store.all_ids()) == 4


def test_counters_include_inactive_sketches_and_features(tmp_path):
    tree = _tree()
    tree.branch_snapshots["future"] = deepcopy(tree.nodes)
    tree.branch_snapshots["future"]["feat-0300"] = FeatureNode(id="feat-0300", name="Later", operation="create_box")
    tree.branch_snapshots["future"]["sketch-0200"] = FeatureNode(id="sketch-0200", name="Later sketch", operation="create_sketch")
    file = tmp_path / "tree.json"
    file.write_text(tree.model_dump_json())
    ctx = RuntimeContext()
    ctx.load_tree_json(str(file))
    assert ctx._new_feature_id() == "feat-0301"
    assert ctx._new_sketch_id() == "sketch-0201"


def test_failed_replay_retains_identity_for_retry_and_clears_errors(tmp_path):
    source = RuntimeContext()
    part = Part(context=source).box(2, 3, 4)
    file = tmp_path / "tree.json"
    source.save_tree_json(str(file))
    ctx = RuntimeContext()
    ctx.load_tree_json(str(file))
    original = ctx.tree.nodes[part.feature_id].replay_shape_id
    ctx.tree = FeatureTreeService.edit_feature(ctx.tree, part.feature_id, {"length": -1})
    ctx.rebuild_tree()
    assert ctx.tree.nodes[part.feature_id].status == "failed"
    assert ctx.tree.nodes[part.feature_id].rebuild_error
    assert ctx.tree.nodes[part.feature_id].replay_shape_id == original
    ctx.tree = FeatureTreeService.edit_feature(ctx.tree, part.feature_id, {"length": 2})
    ctx.rebuild_tree()
    assert ctx.tree.nodes[part.feature_id].shape_id == original
    assert ctx.tree.nodes[part.feature_id].rebuild_error is None


def test_cursors_never_pair_failed_feature_with_another_features_shape():
    ctx = RuntimeContext()
    built = Part(context=ctx).box(2, 3, 4)
    part = Part(context=ctx).box(1, 1, 1)
    ctx.tree = FeatureTreeService.edit_feature(ctx.tree, part.feature_id, {"length": -1})
    ctx.rebuild_tree()
    assert ctx.tree.nodes[part.feature_id].status == "failed"
    assert ctx.last_feature_id == built.feature_id and ctx.last_shape_id == built.shape_id


def test_external_adoption_keeps_cursors_without_claiming_local_ownership():
    client = Mock()
    ctx = RuntimeContext(kernel_client=client)
    tree = _tree()
    ctx.adopt_tree(tree)
    assert ctx.last_feature_id == "moved"
    assert ctx.last_shape_id == "translate-0003"
    assert ctx.kernel.store.all_ids() == []
    assert not ctx._has_shape(ctx.last_shape_id)
    with pytest.raises(NotImplementedError, match="owning in-process kernel"):
        ctx.rebuild_tree()
    client.call_operation.assert_not_called()
