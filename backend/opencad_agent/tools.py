from __future__ import annotations

import logging
import math
import os
from copy import deepcopy
from typing import Any, Callable

from opencad_tree.models import FeatureNode, FeatureTree

logger = logging.getLogger(__name__)

_KERNEL_URL = os.environ.get("OPENCAD_KERNEL_URL", "http://127.0.0.1:8000")
_USE_LIVE_KERNEL = os.environ.get("OPENCAD_AGENT_LIVE_KERNEL", "false").lower() == "true"

KernelCall = Callable[[str, dict[str, Any]], dict[str, Any]]


def _kernel_operation_url(operation: str) -> str:
    base_url = _KERNEL_URL.rstrip("/")
    if not base_url.endswith("/kernel"):
        base_url = f"{base_url}/kernel"
    return f"{base_url}/operations/{operation}"


def _call_kernel(operation: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call the kernel service over HTTP and return the response dict."""
    import httpx

    url = _kernel_operation_url(operation)
    response = httpx.post(url, json={"payload": params}, timeout=30.0)
    response.raise_for_status()
    return response.json()


class ToolRuntime:
    def __init__(
        self,
        tree_state: FeatureTree,
        *,
        kernel_call: KernelCall | None = None,
        live_kernel: bool | None = None,
    ) -> None:
        self.tree = deepcopy(tree_state)
        self._kernel_call = kernel_call
        self._use_live_kernel = live_kernel if live_kernel is not None else (_USE_LIVE_KERNEL or kernel_call is not None)
        self._feature_counter = 1
        self._sketch_counter = 1
        self._shape_counter = 1

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

        for node_id in self.tree.nodes:
            if node_id.startswith("feat-"):
                tail = node_id.split("-")[-1]
                if tail.isdigit():
                    self._feature_counter = max(self._feature_counter, int(tail) + 1)
            if node_id.startswith("sketch-"):
                tail = node_id.split("-")[-1]
                if tail.isdigit():
                    self._sketch_counter = max(self._sketch_counter, int(tail) + 1)

        for node in self.tree.nodes.values():
            if node.shape_id and node.shape_id.startswith("shape-"):
                tail = node.shape_id.split("-")[-1]
                if tail.isdigit():
                    self._shape_counter = max(self._shape_counter, int(tail) + 1)

    def _new_feature_id(self) -> str:
        value = f"feat-{self._feature_counter:04d}"
        self._feature_counter += 1
        return value

    def _new_sketch_id(self) -> str:
        value = f"sketch-{self._sketch_counter:04d}"
        self._sketch_counter += 1
        return value

    def _new_shape_id(self) -> str:
        value = f"shape-{self._shape_counter:04d}"
        self._shape_counter += 1
        return value

    def _entities_to_sketch_segments(
        self,
        entities: dict[str, Any],
        profile_order: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Best-effort conversion from agent entities to kernel sketch segments."""
        segments: list[dict[str, Any]] = []
        points: list[tuple[float, float]] = []

        ordered_entities: list[dict[str, Any]] = []
        seen: set[str] = set()
        if profile_order:
            for entity_id in profile_order:
                entity = entities.get(entity_id)
                if isinstance(entity, dict):
                    ordered_entities.append(entity)
                    seen.add(entity_id)
        for entity_id, entity in entities.items():
            if entity_id in seen:
                continue
            if isinstance(entity, dict):
                ordered_entities.append(entity)

        for entity in ordered_entities:

            kind = str(entity.get("type", "")).lower()
            if kind == "circle":
                cx = entity.get("cx", entity.get("x"))
                cy = entity.get("cy", entity.get("y"))
                radius = entity.get("radius")
                if isinstance(cx, (int, float)) and isinstance(cy, (int, float)) and isinstance(radius, (int, float)):
                    segments.append({"type": "circle", "center": (float(cx), float(cy)), "radius": float(radius)})
                continue

            if kind == "line":
                start = entity.get("start")
                end = entity.get("end")
                if (
                    isinstance(start, (list, tuple))
                    and len(start) == 2
                    and isinstance(end, (list, tuple))
                    and len(end) == 2
                    and isinstance(start[0], (int, float))
                    and isinstance(start[1], (int, float))
                    and isinstance(end[0], (int, float))
                    and isinstance(end[1], (int, float))
                ):
                    segments.append(
                        {
                            "type": "line",
                            "start": (float(start[0]), float(start[1])),
                            "end": (float(end[0]), float(end[1])),
                        }
                    )
                continue

            if kind == "arc":
                start = entity.get("start")
                end = entity.get("end")
                center = entity.get("center")
                radius = entity.get("radius")
                if (
                    isinstance(start, (list, tuple))
                    and len(start) == 2
                    and isinstance(end, (list, tuple))
                    and len(end) == 2
                    and isinstance(center, (list, tuple))
                    and len(center) == 2
                    and isinstance(radius, (int, float))
                ):
                    segments.append(
                        {
                            "type": "arc",
                            "start": (float(start[0]), float(start[1])),
                            "end": (float(end[0]), float(end[1])),
                            "center": (float(center[0]), float(center[1])),
                            "radius": float(radius),
                        }
                    )
                continue

            if kind == "point":
                x = entity.get("x")
                y = entity.get("y")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    points.append((float(x), float(y)))

        # Fallback for legacy point-only payloads.
        if not segments and len(points) >= 2:
            for idx in range(len(points) - 1):
                segments.append({"type": "line", "start": points[idx], "end": points[idx + 1]})
            if len(points) >= 3:
                segments.append({"type": "line", "start": points[-1], "end": points[0]})

        return segments

    def _try_kernel_call(self, operation: str, params: dict[str, Any]) -> str | None:
        if not self._use_live_kernel:
            return None
        try:
            if self._kernel_call is not None:
                result = self._kernel_call(operation, params)
            else:
                result = _call_kernel(operation, params)
            if result.get("ok"):
                return str(result["shape_id"])
        except Exception as exc:
            logger.warning("Kernel call for %s failed, using synthetic ID: %s", operation, exc)
        return None

    def _latest_feature(self) -> str:
        for node_id in reversed(list(self.tree.nodes.keys())):
            if node_id != self.tree.root_id and not self.tree.nodes[node_id].suppressed:
                return node_id
        return self.tree.root_id

    def _require_node(self, node_id: str) -> FeatureNode:
        node = self.tree.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Unknown feature '{node_id}'.")
        if node.suppressed:
            raise ValueError(f"Feature '{node_id}' is suppressed.")
        return node

    def add_sketch(
        self,
        name: str,
        entities: dict[str, Any],
        constraints: list[dict[str, Any]],
        profile_order: list[str] | None = None,
    ) -> str:
        sketch_id = self._new_sketch_id()
        parent = self._latest_feature()
        depends_on = [] if parent == self.tree.root_id else [parent]
        sketch_shape_id: str | None = None

        if self._use_live_kernel:
            segments = self._entities_to_sketch_segments(entities, profile_order)
            if segments:
                resolved = self._try_kernel_call(
                    "create_sketch",
                    {
                        "plane": "XY",
                        "origin": (0.0, 0.0, 0.0),
                        "segments": segments,
                    },
                )
                if resolved:
                    sketch_shape_id = resolved

        node = FeatureNode(
            id=sketch_id,
            name=name,
            operation="add_sketch",
            parameters={
                "entities": entities,
                "constraints": constraints,
                "profile_order": profile_order or [],
            },
            sketch_id=sketch_id,
            depends_on=depends_on,
            shape_id=sketch_shape_id,
            status="built",
        )
        self.tree.nodes[sketch_id] = node
        return sketch_id

    def extrude(self, sketch_id: str, depth: float, name: str) -> str:
        sketch_node = self._require_node(sketch_id)
        feature_id = self._new_feature_id()
        shape_id = self._new_shape_id()

        resolved: str | None = None
        if sketch_node.shape_id:
            resolved = self._try_kernel_call(
                "extrude",
                {"sketch_id": sketch_node.shape_id, "distance": depth, "both": False},
            )
        if not resolved:
            # Fallback keeps current behavior for synthetic sketches or unsupported entity conversion.
            resolved = self._try_kernel_call("create_box", {"length": 40.0, "width": 24.0, "height": depth})
        if resolved:
            shape_id = resolved

        node = FeatureNode(
            id=feature_id,
            name=name,
            operation="extrude",
            parameters={"sketch_id": sketch_id, "depth": depth},
            sketch_id=sketch_id,
            depends_on=[sketch_id],
            shape_id=shape_id,
            status="built",
        )
        self.tree.nodes[feature_id] = node
        return feature_id

    def add_cylinder(self, position: dict[str, float], radius: float, height: float, name: str) -> str:
        feature_id = self._new_feature_id()
        parent = self._latest_feature()
        depends_on = [] if parent == self.tree.root_id else [parent]
        shape_id = self._new_shape_id()

        resolved = self._try_kernel_call("create_cylinder", {"radius": radius, "height": height})
        if resolved:
            shape_id = resolved

        node = FeatureNode(
            id=feature_id,
            name=name,
            operation="add_cylinder",
            parameters={"position": position, "radius": radius, "height": height},
            depends_on=depends_on,
            shape_id=shape_id,
            status="built",
        )
        self.tree.nodes[feature_id] = node
        return feature_id

    def boolean_cut(self, base_id: str, tool_id: str, name: str) -> str:
        base_node = self._require_node(base_id)
        tool_node = self._require_node(tool_id)
        feature_id = self._new_feature_id()
        shape_id = self._new_shape_id()

        if base_node.shape_id and tool_node.shape_id:
            resolved = self._try_kernel_call(
                "boolean_cut",
                {"shape_a_id": base_node.shape_id, "shape_b_id": tool_node.shape_id},
            )
            if resolved:
                shape_id = resolved

        node = FeatureNode(
            id=feature_id,
            name=name,
            operation="boolean_cut",
            parameters={"base_id": base_id, "tool_id": tool_id},
            depends_on=[base_id, tool_id],
            shape_id=shape_id,
            status="built",
        )
        self.tree.nodes[feature_id] = node
        return feature_id

    def fillet_edges(self, shape_id: str, edge_selection: list[str], radius: float, name: str) -> str:
        target_node = self._require_node(shape_id)
        feature_id = self._new_feature_id()
        new_shape_id = self._new_shape_id()

        if target_node.shape_id:
            resolved = self._try_kernel_call(
                "fillet_edges",
                {"shape_id": target_node.shape_id, "edge_ids": edge_selection, "radius": radius},
            )
            if resolved:
                new_shape_id = resolved

        node = FeatureNode(
            id=feature_id,
            name=name,
            operation="fillet",
            parameters={"shape_id": shape_id, "edge_selection": edge_selection, "radius": radius},
            depends_on=[shape_id],
            shape_id=new_shape_id,
            status="built",
        )
        self.tree.nodes[feature_id] = node
        return feature_id

    def get_tree_state(self) -> FeatureTree:
        return deepcopy(self.tree)

    def get_shape_info(self, shape_id: str) -> dict[str, Any]:
        target = None
        for node in self.tree.nodes.values():
            if node.shape_id == shape_id:
                target = node
                break
        if target is None:
            raise ValueError(f"Unknown shape_id '{shape_id}'.")

        # Try the live kernel first for real geometry info
        if self._use_live_kernel and self._kernel_call is None:
            try:
                import httpx

                url = f"{_KERNEL_URL}/shapes/{shape_id}/mesh"
                response = httpx.get(url, params={"deflection": 0.5}, timeout=10.0)
                if response.status_code == 200:
                    mesh = response.json()
                    n_verts = len(mesh.get("vertices", [])) // 3
                    n_faces = len(mesh.get("faces", [])) // 3
                    return {
                        "shape_id": shape_id,
                        "vertices": n_verts,
                        "triangles": n_faces,
                        "has_mesh": True,
                    }
            except Exception as exc:
                logger.warning("Kernel mesh query failed, falling back to heuristic: %s", exc)

        if target.operation == "add_cylinder":
            radius = float(target.parameters.get("radius", 1.0))
            height = float(target.parameters.get("height", 1.0))
            volume = math.pi * radius * radius * height
            surface_area = 2.0 * math.pi * radius * (radius + height)
            dimensions = {"radius": radius, "height": height}
        elif target.operation == "extrude":
            depth = float(target.parameters.get("depth", 1.0))
            width = 40.0
            height = 24.0
            volume = width * height * depth
            surface_area = 2.0 * ((width * height) + (width * depth) + (height * depth))
            dimensions = {"width": width, "height": height, "depth": depth}
        else:
            volume = 100.0
            surface_area = 140.0
            dimensions = {"approx": True}

        return {
            "shape_id": shape_id,
            "dimensions": dimensions,
            "volume": volume,
            "surface_area": surface_area,
        }
