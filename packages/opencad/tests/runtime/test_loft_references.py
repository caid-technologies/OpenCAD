"""Ordered loft references are resolved only in the execution payload."""
from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock

import pytest

from opencad.kernel_adapter import execute_feature_node, resolve_feature_references
from opencad.kernel.operations.schemas import LoftInput
from opencad.tree.models import FeatureNode, FeatureTree
from pydantic import ValidationError


@pytest.fixture()
def tree():
    return FeatureTree(root_id="root", nodes={
        name: FeatureNode(
            id=name, name=name, operation="create_sketch",
            shape_id=f"native-{name}", status="built",
        )
        for name in ("first", "middle", "last")
    })


@pytest.mark.parametrize("order", [
    ["first", "middle", "last"],
    ["last", "middle", "first"],
    ["middle", "first", "middle", "last"],
])
@pytest.mark.parametrize("container", [list, tuple])
def test_profile_list_preserves_order_and_duplicates(tree, order, container):
    params = {"profile_ids": container(order), "solid": True, "ruled": False}
    before = deepcopy(params)
    resolved = resolve_feature_references(params, tree)
    assert resolved == {**before, "profile_ids": [f"native-{name}" for name in order]}
    assert params == before
    assert resolved["profile_ids"] is not params["profile_ids"]
    resolved["profile_ids"].append("only-in-payload")
    assert params == before


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("change", [
    {"status": "pending"}, {"status": "stale"}, {"status": "failed"},
    {"status": "suppressed"}, {"suppressed": True},
    {"shape_id": None}, {"shape_id": ""},
])
def test_every_unavailable_section_is_rejected_before_kernel_call(tree, index, change):
    refs = ["first", "middle", "last"]
    for field, value in change.items():
        setattr(tree.nodes[refs[index]], field, value)
    params = {"profile_ids": refs, "solid": True}
    before = deepcopy(params)
    node = FeatureNode(id="loft", name="Loft", operation="loft", parameters=params)
    registry = Mock()
    with pytest.raises(ValueError, match=rf"profile_ids\[{index}\].*{refs[index]}"):
        execute_feature_node(registry, node, tree)
    registry.call.assert_not_called()
    assert node.parameters == before
    assert params == before, "partially resolved lists must not mutate saved references"


def test_repeated_resolution_uses_latest_shapes_and_keeps_unrelated_values(tree):
    params = {
        "profile_ids": ["middle", "native-literal", "first"],
        "shape_id": "last", "name": "middle", "edge_ids": ["first"],
        "unrelated_profiles": ["first", "middle"],
        "settings": {"profile_ids": ["last"], "profile_id": "middle"},
    }
    before = deepcopy(params)
    for revision in range(3):
        tree.nodes["middle"].shape_id = f"rebuilt-middle-{revision}"
        resolved = resolve_feature_references(params, tree)
        assert resolved == {
            **before, "shape_id": "native-last",
            "profile_ids": [f"rebuilt-middle-{revision}", "native-literal", "native-first"],
        }
        assert params == before
    assert "profile_ids" not in resolve_feature_references({"name": "first"}, tree)


@pytest.mark.parametrize("value", [None, "first", 12, {"first": "last"}, ["first"], ["first", None], ["first", ["last"]]])
def test_invalid_profile_list_values_still_fail_schema_validation(tree, value):
    params = {"profile_ids": value}
    before = deepcopy(params)
    resolved = resolve_feature_references(params, tree)
    with pytest.raises(ValidationError):
        LoftInput.model_validate(resolved)
    assert params == before


def test_feature_executor_sends_ordered_native_ids_without_mutating_tree(tree, monkeypatch):
    params = {"profile_ids": ["last", "middle", "first"], "solid": False, "ruled": True}
    node = FeatureNode(id="loft", name="Loft", operation="loft", parameters=params)
    tree.nodes[node.id] = node
    before = tree.model_dump()
    call = Mock(return_value={"ok": True, "shape_id": "new-loft"})
    monkeypatch.setattr("opencad.kernel_adapter.registry_result_to_dict", call)
    registry = Mock()
    assert execute_feature_node(registry, node, tree) == "new-loft"
    call.assert_called_once_with(registry, "loft", {
        "profile_ids": ["native-last", "native-middle", "native-first"],
        "solid": False, "ruled": True,
    })
    assert tree.model_dump() == before
