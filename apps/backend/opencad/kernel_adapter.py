from __future__ import annotations

from typing import Any

from opencad_kernel.core.models import Success
from opencad_kernel.operations.registry import OperationRegistry
from opencad_tree.models import FeatureNode, FeatureTree

_REFERENCE_KEYS = ("shape_id", "shape_a_id", "shape_b_id", "base_id", "tool_id", "sketch_id")


def normalize_feature_operation(operation: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate feature-tree operation names/params to registry-compatible payloads."""
    mapped_params = dict(params)
    op_name = operation

    if op_name == "fillet":
        op_name = "fillet_edges"
        mapped_params = {
            "shape_id": mapped_params.get("shape_id"),
            "edge_ids": mapped_params.get("edge_selection", []),
            "radius": mapped_params.get("radius"),
        }
    elif op_name == "add_sketch":
        op_name = "create_sketch"
    elif op_name == "add_cylinder":
        op_name = "create_cylinder"
        mapped_params = {
            "radius": mapped_params.get("radius"),
            "height": mapped_params.get("height"),
        }
    elif op_name == "boolean_cut" and "base_id" in mapped_params and "tool_id" in mapped_params:
        mapped_params = {
            "shape_a_id": mapped_params.get("base_id"),
            "shape_b_id": mapped_params.get("tool_id"),
        }

    return op_name, mapped_params


def resolve_feature_references(params: dict[str, Any], tree: FeatureTree) -> dict[str, Any]:
    """Resolve feature-node references in params to concrete shape IDs when available."""
    resolved_params = dict(params)
    for key in _REFERENCE_KEYS:
        value = resolved_params.get(key)
        if isinstance(value, str) and value in tree.nodes:
            resolved = tree.nodes[value].shape_id
            if resolved:
                resolved_params[key] = resolved
    return resolved_params


def registry_result_to_dict(registry: OperationRegistry, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute an operation and return an HTTP-compatible response dict."""
    result = registry.call(operation, payload)
    if isinstance(result, Success):
        return {
            "ok": True,
            "shape_id": result.shape_id,
            "metadata": result.metadata,
        }
    return {
        "ok": False,
        "code": result.code,
        "message": result.message,
        "suggestion": result.suggestion,
    }


def execute_feature_node(registry: OperationRegistry, node: FeatureNode, tree: FeatureTree) -> str:
    """Execute a tree node against the kernel registry and return shape_id."""
    op_name, params = normalize_feature_operation(node.operation, node.parameters)
    params = resolve_feature_references(params, tree)
    response = registry_result_to_dict(registry, op_name, params)
    if not response.get("ok"):
        raise RuntimeError(f"Rebuild failed for '{node.id}': {response.get('message', 'unknown error')}")
    shape_id = response.get("shape_id")
    if not shape_id:
        raise RuntimeError(f"Rebuild failed for '{node.id}': no shape_id returned")
    return str(shape_id)
