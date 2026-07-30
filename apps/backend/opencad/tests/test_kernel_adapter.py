from __future__ import annotations

from opencad.kernel_adapter import (
    normalize_feature_operation,
    registry_result_to_dict,
    resolve_feature_references,
)
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.registry import OperationRegistry
from opencad_tree.models import FeatureNode, FeatureTree


def test_normalize_feature_operation_maps_aliases() -> None:
    op, params = normalize_feature_operation(
        "fillet",
        {"shape_id": "feat-0001", "edge_selection": ["e1"], "radius": 1.0},
    )
    assert op == "fillet_edges"
    assert params == {"shape_id": "feat-0001", "edge_ids": ["e1"], "radius": 1.0}


def test_resolve_feature_references_uses_tree_shape_ids() -> None:
    tree = FeatureTree(
        root_id="root",
        nodes={
            "root": FeatureNode(id="root", name="Root", operation="seed", status="built"),
            "feat-0001": FeatureNode(
                id="feat-0001",
                name="Base",
                operation="create_box",
                shape_id="box-0001",
                status="built",
            ),
        },
    )

    resolved = resolve_feature_references({"shape_id": "feat-0001"}, tree)
    assert resolved["shape_id"] == "box-0001"


def test_registry_result_to_dict_success_shape_id() -> None:
    registry = OperationRegistry(OpenCadKernel(id_strategy="readable"))
    response = registry_result_to_dict(
        registry,
        "create_box",
        {"length": 1.0, "width": 2.0, "height": 3.0},
    )
    assert response["ok"] is True
    assert str(response["shape_id"]).startswith("box-")
