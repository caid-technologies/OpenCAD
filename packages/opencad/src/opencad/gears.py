"""Bounded involute spur gears built with the OpenCAD sketch/solid API.

Flanks and circular arcs are discretized before extrusion. This is a rigid
motion reference, not a hob-generated root fillet or manufacturing standard.
"""
from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opencad import Part, Sketch
from opencad.runtime import RuntimeContext, get_default_context


class SpurGearSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    teeth: int = Field(20, ge=18, le=120, strict=True)
    module_mm: float = Field(2.0, ge=0.5, le=5.0)
    pressure_angle_deg: float = Field(20.0, ge=20.0, le=25.0)
    face_width_mm: float = Field(8.0, gt=0.0, le=50.0)
    bore_diameter_mm: float = Field(6.0, ge=0.0)
    backlash_mm: float = Field(0.1, ge=0.0)

    @model_validator(mode="after")
    def valid_profile(self) -> "SpurGearSpec":
        root = self.module_mm * (self.teeth / 2 - 1.25)
        if self.bore_diameter_mm / 2 >= root - self.module_mm:
            raise ValueError("Gear bore must leave at least one module of root wall.")
        if self.backlash_mm >= self.module_mm * 0.2:
            raise ValueError("Backlash must be smaller than 0.2 module.")
        return self


def spur_gear_outline(spec: SpurGearSpec) -> list[tuple[float, float]]:
    """CCW polygon; total backlash is split equally between the two gears."""
    pitch = spec.module_mm * spec.teeth / 2
    root = pitch - 1.25 * spec.module_mm
    tip = pitch + spec.module_mm
    alpha = math.radians(spec.pressure_angle_deg)
    base = pitch * math.cos(alpha)
    half_pitch = math.pi / (2 * spec.teeth) - spec.backlash_mm / (4 * pitch)
    inv_alpha = math.tan(alpha) - alpha

    def half_angle(radius: float) -> float:
        phi = math.acos(min(1.0, base / radius))
        return half_pitch + inv_alpha - (math.tan(phi) - phi)

    start = max(root, base)
    half_start = half_angle(start)
    half_tip = half_angle(tip)
    points: list[tuple[float, float]] = []

    def add(radius: float, angle: float) -> None:
        point = (radius * math.cos(angle), radius * math.sin(angle))
        if not points or math.dist(points[-1], point) > 1e-10:
            points.append(point)

    for tooth in range(spec.teeth):
        center = tooth * math.tau / spec.teeth
        add(root, center - half_start)
        for step in range(13):
            radius = start + (tip - start) * step / 12
            add(radius, center - half_angle(radius))
        for step in range(1, 7):
            add(tip, center - half_tip + 2 * half_tip * step / 6)
        for step in range(12, -1, -1):
            radius = start + (tip - start) * step / 12
            add(radius, center + half_angle(radius))
        add(root, center + half_start)
        for step in range(1, 7):
            add(root, center + half_start + (math.tau / spec.teeth - 2 * half_start) * step / 6)
    # Last point equals the first at the wrap seam.
    if math.dist(points[0], points[-1]) < 1e-9:
        points.pop()
    return points


def spur_gear(
    spec: SpurGearSpec,
    *,
    center_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
    phase_radians: float = 0.0,
    name: str = "Spur gear",
    context: RuntimeContext | None = None,
) -> Part:
    """Create a separately addressable OpenCAD solid in its rest position."""
    if not all(math.isfinite(v) for v in (*center_mm, phase_radians)):
        raise ValueError("Gear placement must be finite.")
    context = context or get_default_context()
    c, s = math.cos(phase_radians), math.sin(phase_radians)
    points = [(center_mm[0] + x * c - y * s, center_mm[1] + x * s + y * c)
              for x, y in spur_gear_outline(spec)]
    sketch = Sketch(context=context, origin=(0, 0, center_mm[2] - spec.face_width_mm / 2), name=name + " profile")
    for index, point in enumerate(points):
        sketch.line(point, points[(index + 1) % len(points)])
    gear = Part(context=context, name=name).extrude(sketch, depth=spec.face_width_mm, name=name)
    if spec.bore_diameter_mm:
        bore = Sketch(context=context, origin=(0, 0, center_mm[2] - spec.face_width_mm / 2 - 1), name=name + " bore")
        bore.circle(spec.bore_diameter_mm / 2, center=center_mm[:2])
        tool = Part(context=context).extrude(bore, depth=spec.face_width_mm + 2)
        gear = gear.cut(tool, name=name + " bored")
    return gear
