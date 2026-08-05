from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from opencad.kernel.client import KernelClient, LocalKernelClient
from opencad.kernel.core.backend import KernelBackend
from opencad.kernel.core.models import TopologyMap
from opencad.kernel.core.topology import select as select_topology
from opencad.kernel.operations.handlers import OpenCadKernel
from opencad.kernel.operations.registry import OperationRegistry
from opencad.kernel.operations.schemas import SelectorQuery
from opencad.kernel_adapter import execute_feature_node, registry_result_to_dict
from opencad.tree.models import FeatureNode, FeatureTree
from opencad.tree.service import FeatureTreeService

if TYPE_CHECKING:
    from opencad.design_artifact import DesignArtifact


class RuntimeContext:
    """Single-process OpenCAD runtime for headless/fluent usage."""

    def __init__(
        self,
        *,
        id_strategy: str = "readable",
        kernel_client: KernelClient | None = None,
        backend: KernelBackend | None = None,
    ) -> None:
        self._external_kernel = kernel_client
        self.kernel = OpenCadKernel(id_strategy=id_strategy, backend=backend)
        self.registry = OperationRegistry(self.kernel)
        self.tree = FeatureTree(root_id="root")
        self.last_feature_id: str | None = None
        self.last_shape_id: str | None = None
        self._feature_counter = 1
        self._sketch_counter = 1
        self._ensure_root()

    def _ensure_root(self) -> None:
        if self.tree.root_id not in self.tree.nodes:
            root = FeatureNode(
                id=self.tree.root_id,
                name="Root",
                operation="seed",
                parameters={},
                depends_on=[],
                shape_id=None,
                status="built",
            )
            self.tree.nodes[self.tree.root_id] = root

    def _new_feature_id(self) -> str:
        feature_id = f"feat-{self._feature_counter:04d}"
        self._feature_counter += 1
        return feature_id

    def _new_sketch_id(self) -> str:
        sketch_id = f"sketch-{self._sketch_counter:04d}"
        self._sketch_counter += 1
        return sketch_id

    def sync_counters(self) -> None:
        self._feature_counter = 1
        self._sketch_counter = 1
        for node_id in self.tree.nodes:
            if node_id.startswith("feat-"):
                tail = node_id.split("-")[-1]
                if tail.isdigit():
                    self._feature_counter = max(self._feature_counter, int(tail) + 1)
            if node_id.startswith("sketch-"):
                tail = node_id.split("-")[-1]
                if tail.isdigit():
                    self._sketch_counter = max(self._sketch_counter, int(tail) + 1)

    def execute_operation(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        feature_name: str,
        parent_id: str | None = None,
        tool_refs: list[str] | None = None,
        sketch_id: str | None = None,
        tree_parameters: dict[str, Any] | None = None,
        feature_id: str | None = None,
        depends_on: list[str] | None = None,  # back-compat shim
    ) -> tuple[str, str]:
        """Execute a kernel operation and append a built feature node."""
        # Migration shim: if a caller still passes depends_on, derive roles
        # positionally — first entry is the lineage parent, rest are tool refs.
        if depends_on is not None and parent_id is None and tool_refs is None:
            parent_id = depends_on[0] if depends_on else None
            tool_refs = list(depends_on[1:])

        tool_refs = tool_refs or []

        if self._external_kernel is not None:
            response = self._external_kernel.call_operation(operation, payload)
        else:
            response = registry_result_to_dict(self.registry, operation, payload)
        if not response.get("ok"):
            raise RuntimeError(f"Operation '{operation}' failed: {response.get('message', 'unknown error')}")
        shape_id = response.get("shape_id")
        if not shape_id:
            raise RuntimeError(f"Operation '{operation}' returned no shape_id.")
    
        node_id = feature_id
        if node_id is None:
            node_id = self._new_sketch_id() if operation == "create_sketch" else self._new_feature_id()
    
        params = dict(tree_parameters) if tree_parameters is not None else dict(payload)
        node = FeatureNode(
            id=node_id,
            name=feature_name,
            operation=operation,
            parameters=params,
            parent_id=parent_id,
            tool_refs=tool_refs,
            sketch_id=node_id if operation == "create_sketch" else sketch_id,
            shape_id=str(shape_id),
            status="built",
        )
        self.tree = FeatureTreeService.add_feature(self.tree, node)
        self.last_feature_id = node_id
        self.last_shape_id = str(shape_id)
        return node_id, str(shape_id)

    @property
    def kernel_client(self) -> LocalKernelClient:
        """In-process ``KernelClient`` view of this runtime's own kernel."""
        return LocalKernelClient(self.registry, self.kernel)

    def get_topology(self, shape_id: str) -> TopologyMap:
        """Read topology from the same backend that owns the shape."""
        if self._external_kernel is None:
            return self.kernel.get_topology(shape_id)
        return TopologyMap.model_validate(self._external_kernel.get_topology(shape_id))

    def select_subshapes(self, shape_id: str, query: SelectorQuery) -> list[Any]:
        topology = self.get_topology(shape_id)
        return select_topology(topology.faces + topology.edges, query)

    def adopt_tree(self, tree: FeatureTree) -> None:
        """Replace the tree wholesale and resync ID counters and cursors.

        Used by callers that rebuild or hand back tree state from outside —
        for example ``opencad_agent.run_chat``.
        """
        self.tree = tree
        self.sync_counters()

        latest_shape = None
        latest_feature = None
        for node_id, node in self.tree.nodes.items():
            if node_id == self.tree.root_id:
                continue
            latest_feature = node_id
            latest_shape = node.shape_id or latest_shape
        self.last_feature_id = latest_feature
        self.last_shape_id = latest_shape

    def export_step(self, shape_id: str, filepath: str) -> None:
        response = registry_result_to_dict(self.registry, "export_step", {"shape_id": shape_id, "filepath": filepath})
        if not response.get("ok"):
            raise RuntimeError(f"Export failed: {response.get('message', 'unknown error')}")

    def export_stl(self, shape_id: str, filepath: str) -> None:
        response = registry_result_to_dict(self.registry, "export_stl", {"shape_id": shape_id, "filepath": filepath})
        if not response.get("ok"):
            raise RuntimeError(f"Export failed: {response.get('message', 'unknown error')}")

    def serialize_tree(self) -> str:
        return FeatureTreeService.serialize(self.tree)

    def save_tree_json(self, filepath: str) -> None:
        Path(filepath).write_text(self.serialize_tree(), encoding="utf-8")

    def export_design_artifact(
        self,
        filepath: str,
        *,
        artifact_id: str,
        parameters: dict[str, Any] | None = None,
        simulation_tags: list[dict[str, Any]] | None = None,
    ) -> DesignArtifact:
        from opencad.design_artifact import export_design_artifact

        return export_design_artifact(
            filepath,
            artifact_id=artifact_id,
            context=self,
            parameters=parameters,
            simulation_tags=simulation_tags,
        )

    def load_tree_json(self, filepath: str) -> FeatureTree:
        payload = Path(filepath).read_text(encoding="utf-8")
        self.tree = FeatureTreeService.deserialize(payload)
        self._ensure_root()
        self.sync_counters()
        return self.tree

    def _kernel_client_from_tree(self, node: FeatureNode, tree: FeatureTree) -> str:
        return execute_feature_node(self.registry, node, tree)

    def rebuild_tree(self, *, continue_on_error: bool = False) -> FeatureTree:
        self.tree = FeatureTreeService.rebuild(
            self.tree,
            kernel_client=self._kernel_client_from_tree,
            continue_on_error=continue_on_error,
        )
        return self.tree


_DEFAULT_CONTEXT: RuntimeContext | None = None


def get_default_context() -> RuntimeContext:
    global _DEFAULT_CONTEXT
    if _DEFAULT_CONTEXT is None:
        _DEFAULT_CONTEXT = RuntimeContext()
    return _DEFAULT_CONTEXT


def set_default_context(context: RuntimeContext) -> None:
    global _DEFAULT_CONTEXT
    _DEFAULT_CONTEXT = context


def reset_default_context() -> RuntimeContext:
    global _DEFAULT_CONTEXT
    _DEFAULT_CONTEXT = RuntimeContext()
    return _DEFAULT_CONTEXT
