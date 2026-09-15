from __future__ import annotations

from typing import Any

from opencad.kernel.client import result_to_dict
from opencad.kernel.operations.registry import OperationRegistry
from opencad.tree.models import FeatureNode, FeatureTree

_REFERENCE_KEYS = (
    "shape_id", "shape_a_id", "shape_b_id", "base_id", "tool_id", "sketch_id",
    "profile_id", "path_id",
)
_REFERENCE_LIST_KEYS = ("profile_ids",)


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


def _resolve_shape_reference(value: Any, field: str, tree: FeatureTree) -> Any:
    """Resolve one known feature; leave native IDs and invalid types to the kernel."""
    if not isinstance(value, str) or value not in tree.nodes:
        return value
    source = tree.nodes[value]
    if source.suppressed or source.status != "built" or not source.shape_id:
        raise ValueError(
            f"Cannot resolve '{field}' reference to feature '{value}': "
            f"status='{source.status}', suppressed={source.suppressed}; "
            "a built, unsuppressed feature with a shape_id is required."
        )
    return source.shape_id


def resolve_feature_references(params: dict[str, Any], tree: FeatureTree) -> dict[str, Any]:
    """Resolve declared scalar/list references without rewriting saved parameters.

    Known features must be built, unsuppressed, and have a shape ID. Literal
    native IDs remain supported and are validated by the owning kernel.
    Ordered profile lists are copied without sorting or deduplicating; tuple
    inputs are normalized to lists for the registry. Unrelated lists, nested
    settings, and invalid schema values are not recursively rewritten.
    """
    resolved_params = dict(params)
    for key in _REFERENCE_KEYS:
        if key in params:
            resolved_params[key] = _resolve_shape_reference(params[key], key, tree)
    for key in _REFERENCE_LIST_KEYS:
        values = params.get(key)
        if isinstance(values, (list, tuple)):
            resolved_params[key] = [
                _resolve_shape_reference(value, f"{key}[{index}]", tree)
                for index, value in enumerate(values)
            ]
    return resolved_params


def registry_result_to_dict(registry: OperationRegistry, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Execute an operation and return an HTTP-compatible response dict."""
    return result_to_dict(registry.call(operation, payload))


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
