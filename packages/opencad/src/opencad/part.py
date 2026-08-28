from __future__ import annotations

from pathlib import Path
from typing import Any, Self

from opencad.kernel.operations.schemas import SelectorQuery

from opencad.runtime import RuntimeContext, get_default_context
from opencad.sketch import Sketch


class Part:
    """Fluent part API backed by in-process kernel operations."""

    def __init__(self, *, context: RuntimeContext | None = None, name: str = "Part") -> None:
        self._context = context or get_default_context()
        self._name = name
        self.feature_id: str | None = None
        self.shape_id: str | None = None

    @property
    def context(self) -> RuntimeContext:
        return self._context

    def _require_shape(self) -> tuple[str, str]:
        if self.feature_id is None or self.shape_id is None:
            raise ValueError("Part has no active shape. Create or extrude geometry first.")
        return self.feature_id, self.shape_id

    def _apply(
        self,
        operation: str,
        payload: dict,
        *,
        feature_name: str,
        parent_id: str | None = None,
        tool_refs: list[str] | None = None,
        sketch_id: str | None = None,
        tree_parameters: dict | None = None,
        # back-compat shim during migration:
        depends_on: list[str] | None = None,
    ) -> Self:
        # If a caller still passes depends_on, treat first as parent, rest as tools.
        if depends_on is not None and parent_id is None and tool_refs is None:
            parent_id = depends_on[0] if depends_on else None
            tool_refs = list(depends_on[1:])

        feature_id, shape_id = self._context.execute_operation(
            operation,
            payload,
            feature_name=feature_name,
            parent_id=parent_id,
            tool_refs=tool_refs or [],
            sketch_id=sketch_id,
            tree_parameters=tree_parameters,
        )
        self.feature_id = feature_id
        self.shape_id = shape_id
        return self

    def box(self, length: float, width: float, height: float, *, name: str = "Box") -> Self:
        """Create a box centered at the modeling origin."""
        return self._apply(
            "create_box",
            {"length": length, "width": width, "height": height},
            feature_name=name,
            depends_on=[],
        )

    def cylinder(self, radius: float, height: float, *, name: str = "Cylinder") -> Self:
        return self._apply(
            "create_cylinder",
            {"radius": radius, "height": height},
            feature_name=name,
            depends_on=[],
        )

    def translate(
        self,
        offset: tuple[float, float, float],
        *,
        name: str = "Translate",
    ) -> Self:
        """Translate the active shape by ``(dx, dy, dz)``."""
        feature_id, shape_id = self._require_shape()
        return self._apply(
            "translate",
            {"shape_id": shape_id, "offset": offset},
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={"shape_id": feature_id, "offset": offset},
        )

    def sphere(self, radius: float, *, name: str = "Sphere") -> Self:
        return self._apply(
            "create_sphere",
            {"radius": radius},
            feature_name=name,
            depends_on=[],
        )

    def cone(self, radius1: float, radius2: float, height: float, *, name: str = "Cone") -> Self:
        return self._apply(
            "create_cone",
            {"radius1": radius1, "radius2": radius2, "height": height},
            feature_name=name,
            depends_on=[],
        )

    def torus(self, major_radius: float, minor_radius: float, *, name: str = "Torus") -> Self:
        return self._apply(
            "create_torus",
            {"major_radius": major_radius, "minor_radius": minor_radius},
            feature_name=name,
            depends_on=[],
        )

    def extrude(self, sketch: Sketch, *, depth: float, both: bool = False, name: str = "Extrude") -> Self:
        sketch_shape_id = sketch.build()
        if sketch.feature_id is None:
            raise RuntimeError("Sketch was built without a feature ID.")
        return self._apply(
            "extrude",
            {"sketch_id": sketch_shape_id, "distance": depth, "both": both},
            feature_name=name,
            sketch_id=sketch.feature_id,
            tree_parameters={"sketch_id": sketch.feature_id, "distance": depth, "both": both},
        )

    def revolve(
        self,
        sketch: Sketch,
        *,
        axis_origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
        axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0),
        angle: float = 360.0,
        name: str = "Revolve",
    ) -> Self:
        """Sweep a profile around an axis. The profile must not cross the axis."""
        sketch_shape_id = sketch.build()
        if sketch.feature_id is None:
            raise RuntimeError("Sketch was built without a feature ID.")
        return self._apply(
            "revolve",
            {
                "shape_id": sketch_shape_id,
                "axis_origin": axis_origin,
                "axis_direction": axis_direction,
                "angle": angle,
            },
            feature_name=name,
            sketch_id=sketch.feature_id,
            tree_parameters={
                "shape_id": sketch.feature_id,
                "axis_origin": axis_origin,
                "axis_direction": axis_direction,
                "angle": angle,
            },
        )

    def loft(
        self,
        sketches: list[Sketch],
        *,
        solid: bool = True,
        ruled: bool = False,
        name: str = "Loft",
    ) -> Self:
        """Blend through two or more ordered profiles."""
        if len(sketches) < 2:
            raise ValueError("Loft needs at least two profiles.")
        shape_ids = [sketch.build() for sketch in sketches]
        feature_ids = [sketch.feature_id for sketch in sketches]
        if any(feature_id is None for feature_id in feature_ids):
            raise RuntimeError("Sketch was built without a feature ID.")
        return self._apply(
            "loft",
            {"profile_ids": shape_ids, "solid": solid, "ruled": ruled},
            feature_name=name,
            depends_on=feature_ids,
            tree_parameters={
                "profile_ids": feature_ids,
                "solid": solid,
                "ruled": ruled,
            },
        )

    def sweep(self, profile: Sketch, path: Sketch, *, name: str = "Sweep") -> Self:
        """Drag a profile along a path wire."""
        profile_shape_id = profile.build()
        path_shape_id = path.build()
        if profile.feature_id is None or path.feature_id is None:
            raise RuntimeError("Sketch was built without a feature ID.")
        return self._apply(
            "sweep",
            {"profile_id": profile_shape_id, "path_id": path_shape_id},
            feature_name=name,
            depends_on=[profile.feature_id, path.feature_id],
            tree_parameters={
                "profile_id": profile.feature_id,
                "path_id": path.feature_id,
            },
        )

    def union(self, other: Part, *, name: str = "Union") -> Self:
        left_feature, left_shape = self._require_shape()
        right_feature, right_shape = other._require_shape()
        return self._apply(
            "boolean_union",
            {"shape_a_id": left_shape, "shape_b_id": right_shape},
            feature_name=name,
            depends_on=[left_feature, right_feature],
            tree_parameters={"shape_a_id": left_feature, "shape_b_id": right_feature},
        )

    def cut(self, other: Part, *, name: str = "Cut") -> Self:
        left_feature, left_shape = self._require_shape()
        right_feature, right_shape = other._require_shape()
        return self._apply(
            "boolean_cut",
            {"shape_a_id": left_shape, "shape_b_id": right_shape},
            feature_name=name,
            parent_id=left_feature,        # target → lineage
            tool_refs=[right_feature],     # tool → reference only
            tree_parameters={"shape_a_id": left_feature, "shape_b_id": right_feature},
        )

    def intersect(self, other: Part, *, name: str = "Intersection") -> Self:
        left_feature, left_shape = self._require_shape()
        right_feature, right_shape = other._require_shape()
        return self._apply(
            "boolean_intersection",
            {"shape_a_id": left_shape, "shape_b_id": right_shape},
            feature_name=name,
            depends_on=[left_feature, right_feature],
            tree_parameters={"shape_a_id": left_feature, "shape_b_id": right_feature},
        )

    def _resolve_edge_ids(self, edge_spec: list[str] | str | None) -> list[str]:
        _, shape_id = self._require_shape()
        if isinstance(edge_spec, list):
            return edge_spec

        topology = self._context.get_topology(shape_id)
        if edge_spec in (None, "all"):
            return [edge.id for edge in topology.edges]
        if edge_spec == "top":
            # Analytic topology does not carry directional tags on edges yet;
            # returning a deterministic subset keeps API ergonomic.
            return [edge.id for edge in topology.edges[:4]]
        raise ValueError(f"Unsupported edge selector '{edge_spec}'.")

    def fillet(self, *, edges: list[str] | str | None = None, radius: float, name: str = "Fillet") -> Self:
        feature_id, shape_id = self._require_shape()
        edge_ids = self._resolve_edge_ids(edges)
        return self._apply(
            "fillet_edges",
            {"shape_id": shape_id, "edge_ids": edge_ids, "radius": radius},
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={"shape_id": feature_id, "edge_ids": edge_ids, "radius": radius},
        )

    def chamfer(self, *, edges: list[str] | str | None = None, distance: float, name: str = "Chamfer") -> Self:
        feature_id, shape_id = self._require_shape()
        edge_ids = self._resolve_edge_ids(edges)
        return self._apply(
            "chamfer_edges",
            {"shape_id": shape_id, "edge_ids": edge_ids, "distance": distance},
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={"shape_id": feature_id, "edge_ids": edge_ids, "distance": distance},
        )

    def shell(self, *, face_ids: list[str], thickness: float, name: str = "Shell") -> Self:
        feature_id, shape_id = self._require_shape()
        return self._apply(
            "shell",
            {"shape_id": shape_id, "face_ids": face_ids, "thickness": thickness},
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={"shape_id": feature_id, "face_ids": face_ids, "thickness": thickness},
        )

    def draft(
        self,
        *,
        face_ids: list[str],
        angle: float,
        pull_direction: tuple[float, float, float] = (0.0, 0.0, 1.0),
        name: str = "Draft",
    ) -> Self:
        feature_id, shape_id = self._require_shape()
        return self._apply(
            "draft",
            {
                "shape_id": shape_id,
                "face_ids": face_ids,
                "angle": angle,
                "pull_direction": pull_direction,
            },
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={
                "shape_id": feature_id,
                "face_ids": face_ids,
                "angle": angle,
                "pull_direction": pull_direction,
            },
        )

    def offset(self, distance: float, *, name: str = "Offset") -> Self:
        feature_id, shape_id = self._require_shape()
        return self._apply(
            "offset_shape",
            {"shape_id": shape_id, "distance": distance},
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={"shape_id": feature_id, "distance": distance},
        )

    def linear_pattern(
        self,
        *,
        direction: tuple[float, float, float],
        count: int,
        spacing: float,
        name: str = "Linear Pattern",
    ) -> Self:
        feature_id, shape_id = self._require_shape()
        return self._apply(
            "linear_pattern",
            {"shape_id": shape_id, "direction": direction, "count": count, "spacing": spacing},
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={
                "shape_id": feature_id,
                "direction": direction,
                "count": count,
                "spacing": spacing,
            },
        )

    def circular_pattern(
        self,
        *,
        axis_origin: tuple[float, float, float],
        axis_direction: tuple[float, float, float],
        count: int,
        angle: float = 360.0,
        name: str = "Circular Pattern",
    ) -> Self:
        feature_id, shape_id = self._require_shape()
        return self._apply(
            "circular_pattern",
            {
                "shape_id": shape_id,
                "axis_origin": axis_origin,
                "axis_direction": axis_direction,
                "count": count,
                "angle": angle,
            },
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={
                "shape_id": feature_id,
                "axis_origin": axis_origin,
                "axis_direction": axis_direction,
                "count": count,
                "angle": angle,
            },
        )

    def mirror(
        self,
        *,
        plane_origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
        plane_normal: tuple[float, float, float] = (1.0, 0.0, 0.0),
        name: str = "Mirror",
    ) -> Self:
        feature_id, shape_id = self._require_shape()
        return self._apply(
            "mirror",
            {"shape_id": shape_id, "plane_origin": plane_origin, "plane_normal": plane_normal},
            feature_name=name,
            depends_on=[feature_id],
            tree_parameters={
                "shape_id": feature_id,
                "plane_origin": plane_origin,
                "plane_normal": plane_normal,
            },
        )

    def select_faces(self, *, tags: list[str] | None = None, limit: int | None = None) -> list[str]:
        _, shape_id = self._require_shape()
        query = SelectorQuery(kind="face", tags=tags, limit=limit)
        refs = self._context.select_subshapes(shape_id, query)
        return [ref.id for ref in refs]

    def export(self, filepath: str) -> Self:
        """Export the active shape based on the destination extension."""
        suffix = Path(filepath).suffix.lower()
        if suffix in {".step", ".stp"}:
            return self.export_step(filepath)
        if suffix == ".stl":
            return self.export_stl(filepath)
        raise ValueError("Unsupported export format. Use a .step, .stp, or .stl destination.")

    def export_step(self, filepath: str) -> Self:
        _, shape_id = self._require_shape()
        self._context.export_step(shape_id, filepath)
        return self

    def export_stl(self, filepath: str) -> Self:
        _, shape_id = self._require_shape()
        self._context.export_stl(shape_id, filepath)
        return self

    def export_design_artifact(
        self,
        filepath: str,
        *,
        artifact_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        simulation_tags: list[dict[str, Any]] | None = None,
    ) -> Self:
        self._require_shape()
        self._context.export_design_artifact(
            filepath,
            artifact_id=artifact_id or self._name,
            parameters=parameters,
            simulation_tags=simulation_tags,
        )
        return self
