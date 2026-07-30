from __future__ import annotations

from opencad_agent.tools import ToolRuntime
from opencad_kernel.core.models import Success
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.registry import OperationRegistry
from opencad_tree.models import FeatureNode, FeatureTree


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

    def kernel_call(operation: str, payload: dict[str, object]) -> dict[str, object]:
        result = registry.call(operation, payload)
        if isinstance(result, Success):
            return {"ok": True, "shape_id": result.shape_id}
        return {"ok": False, "message": result.message}

    runtime = ToolRuntime(_seed_tree(), kernel_call=kernel_call, live_kernel=True)
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

    out_shape = tree.nodes[feature_id].shape_id
    assert out_shape is not None
    assert str(out_shape).startswith("extrude-")


def test_profile_order_controls_segment_order() -> None:
    kernel = OpenCadKernel(id_strategy="readable")
    registry = OperationRegistry(kernel)
    captured_segments: list[dict[str, object]] = []

    def kernel_call(operation: str, payload: dict[str, object]) -> dict[str, object]:
        nonlocal captured_segments
        if operation == "create_sketch":
            segments = payload.get("segments", [])
            if isinstance(segments, list):
                captured_segments = segments
        result = registry.call(operation, payload)
        if isinstance(result, Success):
            return {"ok": True, "shape_id": result.shape_id}
        return {"ok": False, "message": result.message}

    runtime = ToolRuntime(_seed_tree(), kernel_call=kernel_call, live_kernel=True)
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

    assert captured_segments
    first = captured_segments[0]
    assert first.get("type") == "line"
    assert tuple(first.get("start", ())) == (10.0, 0.0)
    assert tuple(first.get("end", ())) == (10.0, 5.0)
