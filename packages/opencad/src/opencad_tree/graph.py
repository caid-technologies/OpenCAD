from __future__ import annotations

from collections import deque

from opencad_tree.models import FeatureNode

try:  # pragma: no cover - optional dependency
    import networkx as nx
except Exception:  # pragma: no cover
    nx = None


class CircularDependencyError(ValueError):
    pass


class MissingDependencyError(ValueError):
    pass


def _validate_dependencies(nodes: dict[str, FeatureNode]) -> None:
    for node_id, node in nodes.items():
        for parent in node.depends_on:
            if parent not in nodes:
                raise MissingDependencyError(
                    f"Feature node '{node_id}' depends on missing parent '{parent}'."
                )
            if parent == node_id:
                raise CircularDependencyError(f"Feature node '{node_id}' cannot depend on itself.")


def topological_order(nodes: dict[str, FeatureNode]) -> list[str]:
    _validate_dependencies(nodes)

    if nx is not None:  # pragma: no cover - optional dependency
        graph = nx.DiGraph()
        for node_id, node in nodes.items():
            graph.add_node(node_id)
            for parent in node.depends_on:
                graph.add_edge(parent, node_id)
        try:
            return list(nx.topological_sort(graph))
        except nx.NetworkXUnfeasible as exc:
            raise CircularDependencyError("Circular dependency detected.") from exc

    indegree = {node_id: 0 for node_id in nodes}
    adjacency = {node_id: set() for node_id in nodes}

    for node_id, node in nodes.items():
        for parent in node.depends_on:
            adjacency[parent].add(node_id)
            indegree[node_id] += 1

    queue = deque([node_id for node_id, degree in indegree.items() if degree == 0])
    ordered: list[str] = []

    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in adjacency[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered) != len(nodes):
        raise CircularDependencyError("Circular dependency detected.")

    return ordered


def descendants(nodes: dict[str, FeatureNode], source: str) -> set[str]:
    children = {node_id: set() for node_id in nodes}
    for node_id, node in nodes.items():
        for parent in node.depends_on:
            if parent in children:
                children[parent].add(node_id)

    out: set[str] = set()
    stack = [source]
    while stack:
        current = stack.pop()
        for child in children.get(current, set()):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


def direct_dependents(nodes: dict[str, FeatureNode], source: str) -> list[str]:
    return [node_id for node_id, node in nodes.items() if source in node.depends_on]
