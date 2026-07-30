from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from opencad_tree.expression import ExpressionError, evaluate as eval_expr, extract_symbols
from opencad_tree.graph import (
    CircularDependencyError,
    MissingDependencyError,
    descendants,
    direct_dependents,
    topological_order,
)
from opencad_tree.models import FeatureNode, FeatureTree, TypedParameter

KernelClient = Callable[[FeatureNode, FeatureTree], str]


class FeatureTreeService:
    @staticmethod
    def _ensure_active_branch_snapshot(tree: FeatureTree) -> FeatureTree:
        updated = deepcopy(tree)
        if updated.active_branch not in updated.branch_snapshots:
            updated.branch_snapshots[updated.active_branch] = deepcopy(updated.nodes)
        return updated

    @staticmethod
    def _commit_active_branch(tree: FeatureTree) -> FeatureTree:
        updated = FeatureTreeService._ensure_active_branch_snapshot(tree)
        updated.branch_snapshots[updated.active_branch] = deepcopy(updated.nodes)
        updated.revision += 1
        return updated

    @staticmethod
    def _resolve_path(payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise ValueError(f"Unable to resolve path '{path}'.")
        return current

    @staticmethod
    def _cast_value(value: Any, cast_as: str | None) -> Any:
        if cast_as == "int":
            return int(value)
        if cast_as == "float":
            return float(value)
        if cast_as == "bool":
            return bool(value)
        if cast_as == "string":
            return str(value)
        return value

    @staticmethod
    def _runtime_parameters(tree: FeatureTree, node: FeatureNode) -> dict[str, Any]:
        params = dict(node.parameters)
        for key, typed in node.typed_parameters.items():
            params[key] = typed.value

        # First pass: resolve path-based bindings to build a namespace.
        # Bindings with an expression populate the namespace under the leaf
        # name of the source_path instead of directly setting the parameter.
        expr_ns_extras: dict[str, float] = {}
        for binding in node.parameter_bindings:
            resolved_value: Any = None
            if binding.source == "node":
                source_node = tree.nodes.get(binding.source_key)
                if source_node is None:
                    continue
                payload = {
                    "shape_id": source_node.shape_id,
                    "parameters": source_node.parameters,
                }
                resolved_value = FeatureTreeService._resolve_path(payload, binding.source_path)
            elif binding.source == "solver":
                cached = tree.solver_cache.get(binding.source_key)
                if cached is not None:
                    try:
                        resolved_value = FeatureTreeService._resolve_path(cached, binding.source_path)
                    except ValueError:
                        continue
                else:
                    continue

            if binding.expression is not None:
                # Feed into expression namespace under the leaf key name.
                leaf = binding.source_path.rsplit(".", 1)[-1] if binding.source_path else binding.parameter
                if resolved_value is not None and isinstance(resolved_value, (int, float)):
                    expr_ns_extras[leaf] = float(resolved_value)
            else:
                params[binding.parameter] = FeatureTreeService._cast_value(resolved_value, binding.cast_as)

        # Second pass: evaluate expression-based bindings against the
        # namespace built from the first pass.
        expr_ns: dict[str, float] = {
            k: float(v) for k, v in params.items() if isinstance(v, (int, float))
        }
        expr_ns.update(expr_ns_extras)
        for binding in node.parameter_bindings:
            if binding.expression is None:
                continue
            value = eval_expr(binding.expression, expr_ns)
            params[binding.parameter] = FeatureTreeService._cast_value(value, binding.cast_as)
            # Also available for subsequent expressions.
            expr_ns[binding.parameter] = value
        return params

    @staticmethod
    def add_feature(tree: FeatureTree, node: FeatureNode) -> FeatureTree:
        tree = FeatureTreeService._ensure_active_branch_snapshot(tree)
        if node.id in tree.nodes:
            raise ValueError(f"Feature node '{node.id}' already exists.")

        for parent in node.depends_on:
            if parent not in tree.nodes:
                raise ValueError(f"Dependency '{parent}' does not exist.")

        updated = deepcopy(tree)
        updated.nodes[node.id] = node

        # Validate DAG after insertion.
        topological_order(updated.nodes)
        return FeatureTreeService._commit_active_branch(updated)

    @staticmethod
    def edit_feature(tree: FeatureTree, node_id: str, new_params: dict[str, Any]) -> FeatureTree:
        tree = FeatureTreeService._ensure_active_branch_snapshot(tree)
        if node_id not in tree.nodes:
            raise ValueError(f"Feature node '{node_id}' does not exist.")

        updated = deepcopy(tree)
        node = updated.nodes[node_id]
        node.parameters = {**node.parameters, **new_params}
        node.status = "stale"
        node.shape_id = None
        updated.nodes[node_id] = node

        for child_id in descendants(updated.nodes, node_id):
            child = updated.nodes[child_id]
            child.status = "stale"
            child.shape_id = None
            updated.nodes[child_id] = child

        return FeatureTreeService._commit_active_branch(updated)

    @staticmethod
    def set_typed_parameters(
        tree: FeatureTree,
        node_id: str,
        typed_parameters: dict[str, dict[str, Any]],
    ) -> FeatureTree:
        tree = FeatureTreeService._ensure_active_branch_snapshot(tree)
        if node_id not in tree.nodes:
            raise ValueError(f"Feature node '{node_id}' does not exist.")

        updated = deepcopy(tree)
        node = updated.nodes[node_id]
        for key, payload in typed_parameters.items():
            param_type = payload.get("type")
            if not param_type:
                raise ValueError(f"Typed parameter '{key}' requires a type.")
            node.typed_parameters[key] = TypedParameter(type=param_type, value=payload.get("value"))
            node.parameters[key] = payload.get("value")

        node.status = "stale"
        node.shape_id = None
        updated.nodes[node_id] = node

        for child_id in descendants(updated.nodes, node_id):
            child = updated.nodes[child_id]
            child.status = "stale"
            child.shape_id = None
            updated.nodes[child_id] = child

        return FeatureTreeService._commit_active_branch(updated)

    @staticmethod
    def suppress_feature(tree: FeatureTree, node_id: str, suppressed: bool = True) -> FeatureTree:
        tree = FeatureTreeService._ensure_active_branch_snapshot(tree)
        if node_id not in tree.nodes:
            raise ValueError(f"Feature node '{node_id}' does not exist.")

        updated = deepcopy(tree)
        node = updated.nodes[node_id]
        node.suppressed = suppressed
        node.status = "suppressed" if suppressed else "stale"
        node.shape_id = None
        updated.nodes[node_id] = node

        desc = descendants(updated.nodes, node_id)
        # Process in topological order so parents are updated before children.
        desc_ordered = [n for n in topological_order(updated.nodes) if n in desc]
        for child_id in desc_ordered:
            child = updated.nodes[child_id]
            child.shape_id = None
            if suppressed:
                # A node is transitively suppressed only when ALL its
                # parents are suppressed.  If any parent is not suppressed
                # the node is merely stale (blocked by a suppressed parent).
                all_parents_suppressed = all(
                    updated.nodes[p].suppressed for p in child.depends_on
                )
                child.suppressed = all_parents_suppressed
                child.status = "suppressed" if all_parents_suppressed else "stale"
            else:
                child.suppressed = False
                child.status = "stale"
            updated.nodes[child_id] = child

        return FeatureTreeService._commit_active_branch(updated)

    @staticmethod
    def delete_feature(tree: FeatureTree, node_id: str, cascade: bool = False) -> FeatureTree:
        tree = FeatureTreeService._ensure_active_branch_snapshot(tree)
        if node_id not in tree.nodes:
            raise ValueError(f"Feature node '{node_id}' does not exist.")
        if node_id == tree.root_id:
            raise ValueError("Cannot delete root node.")

        deps = direct_dependents(tree.nodes, node_id)
        if deps and not cascade:
            raise ValueError(
                f"Cannot delete node '{node_id}' because dependents exist: {', '.join(deps)}"
            )

        to_delete = {node_id}
        if cascade:
            to_delete |= descendants(tree.nodes, node_id)

        updated = deepcopy(tree)
        for doomed in to_delete:
            updated.nodes.pop(doomed, None)

        return FeatureTreeService._commit_active_branch(updated)

    @staticmethod
    def create_branch(tree: FeatureTree, branch_name: str, from_branch: str | None = None) -> FeatureTree:
        if not branch_name:
            raise ValueError("Branch name is required.")

        updated = FeatureTreeService._ensure_active_branch_snapshot(tree)
        source = from_branch or updated.active_branch
        if source not in updated.branch_snapshots:
            raise ValueError(f"Branch '{source}' does not exist.")
        if branch_name in updated.branch_snapshots:
            raise ValueError(f"Branch '{branch_name}' already exists.")

        updated.branch_snapshots[branch_name] = deepcopy(updated.branch_snapshots[source])
        updated.revision += 1
        return updated

    @staticmethod
    def switch_branch(tree: FeatureTree, branch_name: str) -> FeatureTree:
        updated = FeatureTreeService._ensure_active_branch_snapshot(tree)
        snapshot = updated.branch_snapshots.get(branch_name)
        if snapshot is None:
            raise ValueError(f"Branch '{branch_name}' does not exist.")
        updated.active_branch = branch_name
        updated.nodes = deepcopy(snapshot)
        return updated

    @staticmethod
    def list_branches(tree: FeatureTree) -> list[str]:
        updated = FeatureTreeService._ensure_active_branch_snapshot(tree)
        return sorted(updated.branch_snapshots.keys())

    @staticmethod
    def _invalidate_expression_dependents(
        nodes: dict[str, FeatureNode],
        changed_params: set[str],
    ) -> set[str]:
        """Find nodes whose expression bindings reference *changed_params*.

        Returns the set of additionally-staled node IDs.
        """
        staled: set[str] = set()
        for node_id, node in nodes.items():
            for binding in node.parameter_bindings:
                if binding.expression is None:
                    continue
                try:
                    symbols = extract_symbols(binding.expression)
                except ExpressionError:
                    continue
                if symbols & changed_params:
                    if node.status != "suppressed":
                        node.status = "stale"
                        node.shape_id = None
                    staled.add(node_id)
        return staled

    @staticmethod
    def apply_solver_result(tree: FeatureTree, sketch_id: str, solved_sketch: dict[str, Any]) -> FeatureTree:
        tree = FeatureTreeService._ensure_active_branch_snapshot(tree)
        updated = deepcopy(tree)
        updated.solver_cache[sketch_id] = solved_sketch

        stale_roots: set[str] = set()
        changed_param_names: set[str] = set()
        for node_id, node in updated.nodes.items():
            changed = False
            for binding in node.parameter_bindings:
                if binding.source != "solver" or binding.source_key != sketch_id:
                    continue
                if binding.expression is not None:
                    continue  # expressions resolved at runtime, not here
                value = FeatureTreeService._resolve_path(solved_sketch, binding.source_path)
                coerced = FeatureTreeService._cast_value(value, binding.cast_as)
                old_value = node.parameters.get(binding.parameter)
                node.parameters[binding.parameter] = coerced
                if binding.parameter in node.typed_parameters:
                    node.typed_parameters[binding.parameter].value = coerced
                if old_value != coerced:
                    changed = True
                    changed_param_names.add(binding.parameter)
            if changed:
                node.status = "stale"
                node.shape_id = None
                updated.nodes[node_id] = node
                stale_roots.add(node_id)

        for root in stale_roots:
            for child_id in descendants(updated.nodes, root):
                child = updated.nodes[child_id]
                child.status = "stale"
                child.shape_id = None
                updated.nodes[child_id] = child

        # Expression-dependency invalidation: any node whose expression
        # references a parameter that just changed also goes stale.
        if changed_param_names:
            expr_staled = FeatureTreeService._invalidate_expression_dependents(
                updated.nodes, changed_param_names,
            )
            for extra_root in expr_staled - stale_roots:
                for child_id in descendants(updated.nodes, extra_root):
                    child = updated.nodes[child_id]
                    if child.status != "suppressed":
                        child.status = "stale"
                        child.shape_id = None
                    updated.nodes[child_id] = child

        return FeatureTreeService._commit_active_branch(updated)

    @staticmethod
    def rebuild(
        tree: FeatureTree,
        kernel_client: KernelClient,
        continue_on_error: bool = False,
    ) -> FeatureTree:
        updated = deepcopy(tree)
        updated = FeatureTreeService._ensure_active_branch_snapshot(updated)
        order = topological_order(updated.nodes)

        for node_id in order:
            node = updated.nodes[node_id]

            if node.suppressed:
                node.status = "suppressed"
                node.shape_id = None
                updated.nodes[node_id] = node
                continue

            # If a parent failed, this branch cannot build.
            parent_blocked = any(updated.nodes[parent].status != "built" for parent in node.depends_on)
            if parent_blocked:
                node.status = "stale"
                node.shape_id = None
                updated.nodes[node_id] = node
                continue

            if node.status == "built":
                continue

            if node.status not in {"pending", "stale", "failed"}:
                continue

            try:
                runtime_node = deepcopy(node)
                runtime_node.parameters = FeatureTreeService._runtime_parameters(updated, node)
                shape_id = kernel_client(runtime_node, updated)
                node.shape_id = shape_id
                node.parameters = runtime_node.parameters
                node.status = "built"
                updated.nodes[node_id] = node
            except Exception:
                node.status = "failed"
                node.shape_id = None
                updated.nodes[node_id] = node

                for child_id in descendants(updated.nodes, node_id):
                    child = updated.nodes[child_id]
                    child.status = "stale"
                    child.shape_id = None
                    updated.nodes[child_id] = child

                if not continue_on_error:
                    break

        return FeatureTreeService._commit_active_branch(updated)

    @staticmethod
    def serialize(tree: FeatureTree) -> str:
        return tree.model_dump_json(indent=2)

    @staticmethod
    def deserialize(data: str) -> FeatureTree:
        tree = FeatureTree.model_validate_json(data)
        tree = FeatureTreeService._ensure_active_branch_snapshot(tree)
        # Validate DAG on load.
        topological_order(tree.nodes)
        return tree

    @staticmethod
    def ensure_acyclic(tree: FeatureTree) -> None:
        try:
            topological_order(tree.nodes)
        except CircularDependencyError as exc:
            raise ValueError("Circular dependency detected.") from exc
        except MissingDependencyError as exc:
            raise ValueError(str(exc)) from exc

    # ── Assembly mate convenience ───────────────────────────────────

    @staticmethod
    def add_mate_feature(
        tree: FeatureTree,
        mate_node_id: str,
        mate_name: str,
        mate_id: str,
        source_node_ids: list[str],
        parameters: dict[str, Any] | None = None,
    ) -> FeatureTree:
        """Add an assembly-mate feature node that depends on the mated shapes.

        When either source shape rebuilds, this mate node goes stale and
        must be re-evaluated.
        """
        node = FeatureNode(
            id=mate_node_id,
            name=mate_name,
            operation="assembly_mate",
            parameters=parameters or {},
            depends_on=source_node_ids,
            mate_id=mate_id,
            is_assembly_mate=True,
        )
        return FeatureTreeService.add_feature(tree, node)

    @staticmethod
    def stale_mates(tree: FeatureTree) -> list[FeatureNode]:
        """Return all assembly-mate nodes currently in stale/failed state."""
        return [
            node
            for node in tree.nodes.values()
            if node.is_assembly_mate and node.status in ("stale", "failed")
        ]
