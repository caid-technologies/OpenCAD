"""Prepare serialized feature metadata for replay in its receiving kernel.

Geometry is not stored in a FeatureTree. Session identity permits warm cache
reuse; a foreign/legacy tree must execute again, preserving saved result IDs
only through the registry's checked replay mechanism.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from opencad.kernel_adapter import _REFERENCE_KEYS, _REFERENCE_LIST_KEYS
from opencad.tree.graph import topological_order
from opencad.tree.models import FeatureNode, FeatureTree


def _is_root(node: FeatureNode, root_id: str) -> bool:
    return node.id == root_id and node.operation == "seed" and not node.depends_on


def _check_portable_references(nodes: dict[str, FeatureNode], root_id: str) -> None:
    """Raw IDs are portable only when a saved producer can reconstruct them.

    In particular, never accidentally resolve an unknown raw ID to an unrelated
    readable ID allocated later in the new kernel. Imported files are validated
    by their import operation, not opened while parsing a tree.
    """
    produced = {n.replay_shape_id or n.shape_id for n in nodes.values()} - {None}
    for node in nodes.values():
        if _is_root(node, root_id):
            continue
        params = {**node.parameters, **{k: v.value for k, v in node.typed_parameters.items()}}
        bound = {b.parameter for b in node.parameter_bindings}
        values = [(key, params[key]) for key in _REFERENCE_KEYS if key in params and key not in bound]
        for key in _REFERENCE_LIST_KEYS:
            if key not in bound and isinstance(params.get(key), (list, tuple)):
                values.extend((f"{key}[{i}]", value) for i, value in enumerate(params[key]))
        for field, value in values:
            if isinstance(value, str) and value not in nodes and value not in produced:
                raise ValueError(
                    f"Cannot cold-load feature '{node.id}': '{field}' refers to external "
                    f"shape '{value}' with no saved producer. Import its source or use a feature reference."
                )
        for key in ("edge_ids", "edge_selection", "face_ids"):
            selections = params.get(key, [])
            if not isinstance(selections, (list, tuple)):
                continue  # Registry validation retains ownership of malformed values.
            for ref in selections:
                if isinstance(ref, str) and (":edge:" in ref or ":face:" in ref):
                    owner = ref.rsplit(":", 2)[0]
                    if owner not in produced:
                        raise ValueError(f"Cannot cold-load feature '{node.id}': no saved producer for '{ref}'.")


def prepare_tree(
    tree: FeatureTree,
    *,
    session_id: str,
    has_shape: Callable[[str], bool],
    occupied_ids: set[str],
) -> FeatureTree:
    """Copy and invalidate unavailable geometry, including inactive snapshots.

    Cold replay never overwrites a receiving kernel's existing identities.
    Availability is checked before any operations create new geometry.
    """
    updated = deepcopy(tree)
    foreign = updated.kernel_session_id != session_id
    snapshots = [updated.nodes, *updated.branch_snapshots.values()]
    if foreign:
        targets = {
            n.replay_shape_id or n.shape_id
            for nodes in snapshots for n in nodes.values()
            if not _is_root(n, updated.root_id)
        } - {None}
        collisions = targets & occupied_ids
        if collisions:
            raise ValueError(
                "Cannot cold-load: saved shape IDs collide with the receiving kernel: "
                f"{', '.join(sorted(collisions))}. Use a fresh RuntimeContext; existing geometry was not changed."
            )
        for nodes in snapshots:
            _check_portable_references(nodes, updated.root_id)

    for nodes in snapshots:
        # Validate each branch and use dependency order, not dictionary order.
        for node_id in topological_order(nodes):
            node = nodes[node_id]
            if _is_root(node, updated.root_id):
                node.status, node.shape_id = "built", None
                node.replay_shape_id = None
                node.rebuild_error = None
                continue
            missing = node.status == "built" and (not node.shape_id or not has_shape(node.shape_id))
            blocked = any(nodes[parent].status != "built" for parent in node.depends_on)
            if foreign or missing or blocked:
                # Preserve the identity only if no live result would be overwritten.
                if node.shape_id and (foreign or not has_shape(node.shape_id)):
                    node.replay_shape_id = node.shape_id
                node.shape_id = None
                node.status = "suppressed" if node.suppressed else "stale"
                node.rebuild_error = None
            if node.suppressed:
                node.shape_id, node.status, node.rebuild_error = None, "suppressed", None
    updated.kernel_session_id = session_id
    updated.branch_snapshots[updated.active_branch] = deepcopy(updated.nodes)
    return updated
