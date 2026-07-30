from __future__ import annotations

from math import pi

from .models import BoundingBox


def box_bbox(length: float, width: float, height: float) -> BoundingBox:
    return BoundingBox(
        min_x=0.0,
        min_y=0.0,
        min_z=0.0,
        max_x=length,
        max_y=width,
        max_z=height,
    )


def cylinder_bbox(radius: float, height: float) -> BoundingBox:
    return BoundingBox(
        min_x=-radius,
        min_y=-radius,
        min_z=0.0,
        max_x=radius,
        max_y=radius,
        max_z=height,
    )


def sphere_bbox(radius: float) -> BoundingBox:
    return BoundingBox(
        min_x=-radius,
        min_y=-radius,
        min_z=-radius,
        max_x=radius,
        max_y=radius,
        max_z=radius,
    )


def overlap_bbox(a: BoundingBox, b: BoundingBox) -> BoundingBox:
    return BoundingBox(
        min_x=max(a.min_x, b.min_x),
        min_y=max(a.min_y, b.min_y),
        min_z=max(a.min_z, b.min_z),
        max_x=min(a.max_x, b.max_x),
        max_y=min(a.max_y, b.max_y),
        max_z=min(a.max_z, b.max_z),
    )


def overlap_volume(a: BoundingBox, b: BoundingBox) -> float:
    return overlap_bbox(a, b).volume()


def union_bbox(a: BoundingBox, b: BoundingBox) -> BoundingBox:
    return BoundingBox(
        min_x=min(a.min_x, b.min_x),
        min_y=min(a.min_y, b.min_y),
        min_z=min(a.min_z, b.min_z),
        max_x=max(a.max_x, b.max_x),
        max_y=max(a.max_y, b.max_y),
        max_z=max(a.max_z, b.max_z),
    )


def box_volume(length: float, width: float, height: float) -> float:
    return length * width * height


def cylinder_volume(radius: float, height: float) -> float:
    return pi * radius * radius * height


def sphere_volume(radius: float) -> float:
    return (4.0 / 3.0) * pi * (radius**3)
