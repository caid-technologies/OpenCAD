from __future__ import annotations

from typing import Self

from opencad_kernel.operations.schemas import SketchSegment

from opencad.runtime import RuntimeContext, get_default_context


class Sketch:
    """Fluent sketch builder backed by `create_sketch`."""

    def __init__(
        self,
        *,
        context: RuntimeContext | None = None,
        plane: str = "XY",
        origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
        name: str = "Sketch",
    ) -> None:
        self._context = context or get_default_context()
        self._plane = plane
        self._origin = origin
        self._name = name
        self._segments: list[SketchSegment] = []
        self._entities: dict[str, dict[str, object]] = {}
        self._profile_order: list[str] = []
        self._entity_counter = 1
        self.feature_id: str | None = None
        self.shape_id: str | None = None

    @property
    def context(self) -> RuntimeContext:
        return self._context

    def _new_entity_id(self, prefix: str) -> str:
        entity_id = f"{prefix}-{self._entity_counter:04d}"
        self._entity_counter += 1
        return entity_id

    def line(self, start: tuple[float, float], end: tuple[float, float]) -> Self:
        entity_id = self._new_entity_id("line")
        self._segments.append(SketchSegment(type="line", start=start, end=end))
        self._entities[entity_id] = {
            "id": entity_id,
            "type": "line",
            "start": start,
            "end": end,
        }
        self._profile_order.append(entity_id)
        return self

    def rect(self, width: float, height: float, *, origin: tuple[float, float] = (0.0, 0.0)) -> Self:
        ox, oy = origin
        p1 = (ox, oy)
        p2 = (ox + width, oy)
        p3 = (ox + width, oy + height)
        p4 = (ox, oy + height)
        self.line(p1, p2)
        self.line(p2, p3)
        self.line(p3, p4)
        self.line(p4, p1)
        return self

    def circle(
        self,
        radius: float,
        *,
        center: tuple[float, float] = (0.0, 0.0),
        subtract: bool = False,
    ) -> Self:
        entity_id = self._new_entity_id("circle")
        segment = SketchSegment(type="circle", center=center, radius=radius)
        self._segments.append(segment)
        self._entities[entity_id] = {
            "id": entity_id,
            "type": "circle",
            "center": center,
            "radius": radius,
            "subtract": subtract,
        }
        self._profile_order.append(entity_id)
        return self

    def build(self) -> str:
        if self.shape_id is not None:
            return self.shape_id
        payload = {
            "plane": self._plane,
            "origin": self._origin,
            "segments": [segment.model_dump() for segment in self._segments],
        }
        tree_parameters = {
            "plane": self._plane,
            "origin": self._origin,
            "segments": payload["segments"],
            "entities": self._entities,
            "profile_order": self._profile_order,
            "constraints": [],
        }
        feature_id, shape_id = self._context.execute_operation(
            "create_sketch",
            payload,
            feature_name=self._name,
            depends_on=[],
            tree_parameters=tree_parameters,
        )
        self.feature_id = feature_id
        self.shape_id = shape_id
        return shape_id
