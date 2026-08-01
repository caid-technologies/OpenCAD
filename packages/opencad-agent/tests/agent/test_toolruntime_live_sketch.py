from __future__ import annotations

from opencad_agent.tools import ToolRuntime
from opencad.kernel.client import LocalKernelClient
from opencad.kernel.operations.handlers import OpenCadKernel
from opencad.kernel.operations.registry import OperationRegistry
from opencad.tree.models import FeatureNode, FeatureTree


class _RecordingKernelClient(LocalKernelClient):
    """LocalKernelClient that captures the segments sent to ``create_sketch``."""

    def __init__(self, registry: OperationRegistry) -> None:
        super().__init__(registry)
        self.segments: list[dict[str, object]] = []

    def call_operation(self, operation: str, params: dict[str, object]) -> dict[str, object]:
        if operation == "create_sketch":
            segments = params.get("segments", [])
            if isinstance(segments, list):
                self.segments = segments
        return super().call_operation(operation, params)


def _seed_tree() -> FeatureTree:
    return FeatureTree(
        root_id="root",
        nodes={
            "root": FeatureNode(
                id="root",
                name="Root",
                operation="seed",
                parameters={},
                depends_on=[],
                status="built",
                shape_id=None,
            )
        },
    )


def test_live_mode_creates_sketch_shape_then_extrudes() -> None:
    kernel = OpenCadKernel(id_strategy="readable")
    registry = OperationRegistry(kernel)

    runtime = ToolRuntime(_seed_tree(), kernel_client=LocalKernelClient(registry), live_kernel=True)
    sketch_id = runtime.add_sketch(
        name="Rect",
        entities={
            "l1": {"id": "l1", "type": "line", "start": (0.0, 0.0), "end": (10.0, 0.0)},
            "l2": {"id": "l2", "type": "line", "start": (10.0, 0.0), "end": (10.0, 5.0)},
            "l3": {"id": "l3", "type": "line", "start": (10.0, 5.0), "end": (0.0, 5.0)},
            "l4": {"id": "l4", "type": "line", "start": (0.0, 5.0), "end": (0.0, 0.0)},
        },
        constraints=[],
    )

    feature_id = runtime.extrude(sketch_id=sketch_id, depth=7.0, name="Base")
    tree = runtime.get_tree_state()

    assert tree.nodes[sketch_id].shape_id is not None
    assert str(tree.nodes[sketch_id].shape_id).startswith("sketch-")
    assert tree.nodes[sketch_id].parent_id is None

    out_shape = tree.nodes[feature_id].shape_id
    assert out_shape is not None
    assert str(out_shape).startswith("extrude-")
    assert tree.nodes[feature_id].parent_id is None
    assert tree.nodes[feature_id].sketch_id == sketch_id
    assert tree.nodes[feature_id].depends_on == [sketch_id]


def test_profile_order_controls_segment_order() -> None:
    kernel = OpenCadKernel(id_strategy="readable")
    registry = OperationRegistry(kernel)
    client = _RecordingKernelClient(registry)

    runtime = ToolRuntime(_seed_tree(), kernel_client=client, live_kernel=True)
    runtime.add_sketch(
        name="Ordered Rect",
        entities={
            "l1": {"id": "l1", "type": "line", "start": (0.0, 0.0), "end": (10.0, 0.0)},
            "l2": {"id": "l2", "type": "line", "start": (10.0, 0.0), "end": (10.0, 5.0)},
            "l3": {"id": "l3", "type": "line", "start": (10.0, 5.0), "end": (0.0, 5.0)},
            "l4": {"id": "l4", "type": "line", "start": (0.0, 5.0), "end": (0.0, 0.0)},
        },
        constraints=[],
        profile_order=["l2", "l3", "l4", "l1"],
    )

    assert client.segments
    first = client.segments[0]
    assert first.get("type") == "line"
    assert tuple(first.get("start", ())) == (10.0, 0.0)
    assert tuple(first.get("end", ())) == (10.0, 5.0)
