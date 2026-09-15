"""Scalar reference contracts; these tests do not require OCCT."""
from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock

import pytest

from opencad.kernel_adapter import execute_feature_node, resolve_feature_references
from opencad.tree.models import FeatureNode, FeatureTree


@pytest.fixture()
def tree():
    return FeatureTree(root_id="root", nodes={
        "section": FeatureNode(
            id="section", name="Section", operation="create_sketch",
            shape_id="native-section", status="built",
        ),
        "spine": FeatureNode(
            id="spine", name="Spine", operation="create_sketch",
            shape_id="native-spine", status="built",
        ),
    })


@pytest.mark.parametrize("key", [
    "shape_id", "shape_a_id", "shape_b_id", "base_id", "tool_id", "sketch_id",
    "profile_id", "path_id",
])
def test_scalar_resolution_copies_parameters_and_uses_current_shape(tree, key):
    params = {key: "section", "name": "section", "unrelated_list": ["section"]}
    original = deepcopy(params)
    assert resolve_feature_references(params, tree) == {
        **original, key: "native-section",
    }
    tree.nodes["section"].shape_id = "rebuilt-section"
    assert resolve_feature_references(params, tree)[key] == "rebuilt-section"
    assert params == original, "saved feature references must not become native IDs"


@pytest.mark.parametrize("key", ["profile_id", "path_id"])
@pytest.mark.parametrize("status", ["pending", "stale", "failed", "suppressed"])
def test_sweep_reference_rejects_unbuilt_feature_even_with_cached_shape(tree, key, status):
    tree.nodes["section"].status = status
    with pytest.raises(ValueError, match=rf"{key}.*section.*{status}"):
        resolve_feature_references({key: "section"}, tree)


@pytest.mark.parametrize("key", ["profile_id", "path_id"])
@pytest.mark.parametrize("change", [{"suppressed": True}, {"shape_id": None}])
def test_built_status_alone_does_not_certify_reference(tree, key, change):
    for name, value in change.items():
        setattr(tree.nodes["section"], name, value)
    with pytest.raises(ValueError, match=rf"{key}.*section"):
        resolve_feature_references({key: "section"}, tree)


def test_mixed_native_and_feature_ids_leave_unrelated_strings_and_lists_alone(tree):
    params = {"profile_id": "section", "path_id": "native-spine",
              "name": "spine", "unrelated_profiles": ["section", "spine"],
              "settings": {"path_id": "spine"}}
    before = deepcopy(params)
    assert resolve_feature_references(params, tree) == {**before, "profile_id": "native-section"}
    assert params == before


def test_invalid_schema_values_are_left_for_registry_validation(tree):
    params = {"profile_id": None, "path_id": ["spine"]}
    assert resolve_feature_references(params, tree) == params


@pytest.mark.parametrize("key", ["profile_id", "path_id"])
def test_unavailable_sweep_reference_never_reaches_kernel(tree, key):
    params = {"profile_id": "section", "path_id": "spine"}
    tree.nodes[params[key]].status = "stale"
    node = FeatureNode(id="sweep", name="Sweep", operation="sweep", parameters=params)
    registry = Mock()
    with pytest.raises(ValueError, match=key):
        execute_feature_node(registry, node, tree)
    registry.call.assert_not_called()
    assert node.parameters == params
