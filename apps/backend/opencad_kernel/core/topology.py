"""Stable topology naming — assigns deterministic names to faces and edges.

The naming system ensures subshape references survive parametric rebuilds by
tagging faces/edges with semantic labels derived from their geometric
properties (normal direction, centroid, area, etc.).

**Scope decision (v1):**  This module provides *capability parity* with
Build123d's topology selectors.  Fluent builder syntax and workplane-centric
UX are deferred to a future milestone.
"""

from __future__ import annotations

import math
from typing import Any

from opencad_kernel.core.models import (
    BoundingBox,
    SubshapeKind,
    SubshapeRef,
    TopologyMap,
)
from opencad_kernel.operations.schemas import SelectorQuery

# ── Direction → tag mapping ─────────────────────────────────────────

_DIRECTION_TAGS: list[tuple[tuple[float, float, float], list[str]]] = [
    ((0.0, 0.0, 1.0), ["top", "+Z"]),
    ((0.0, 0.0, -1.0), ["bottom", "-Z"]),
    ((0.0, 1.0, 0.0), ["front", "+Y"]),
    ((0.0, -1.0, 0.0), ["back", "-Y"]),
    ((1.0, 0.0, 0.0), ["right", "+X"]),
    ((-1.0, 0.0, 0.0), ["left", "-X"]),
]

_COS_THRESHOLD = 0.95  # ~18° tolerance for direction matching


def _vec_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vec_len(v: tuple[float, float, float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _vec_normalise(v: tuple[float, float, float]) -> tuple[float, float, float]:
    ln = _vec_len(v)
    if ln < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / ln, v[1] / ln, v[2] / ln)


def _auto_tags_for_normal(normal: tuple[float, float, float] | None) -> list[str]:
    """Return semantic direction tags for a face normal."""
    if normal is None:
        return []
    nn = _vec_normalise(normal)
    tags: list[str] = []
    for direction, labels in _DIRECTION_TAGS:
        if _vec_dot(nn, direction) >= _COS_THRESHOLD:
            tags.extend(labels)
            break
    return tags


# ── Synthetic topology (analytic backend) ───────────────────────────


def synthetic_box_faces(shape_id: str, bbox: BoundingBox) -> list[SubshapeRef]:
    """Generate the 6 canonical faces of an axis-aligned box."""
    cx = (bbox.min_x + bbox.max_x) / 2
    cy = (bbox.min_y + bbox.max_y) / 2
    cz = (bbox.min_z + bbox.max_z) / 2
    dx = bbox.max_x - bbox.min_x
    dy = bbox.max_y - bbox.min_y
    dz = bbox.max_z - bbox.min_z

    face_defs: list[tuple[tuple[float, float, float], tuple[float, float, float], float]] = [
        # centroid, normal, area
        ((cx, cy, bbox.max_z), (0, 0, 1), dx * dy),     # top
        ((cx, cy, bbox.min_z), (0, 0, -1), dx * dy),    # bottom
        ((cx, bbox.max_y, cz), (0, 1, 0), dx * dz),     # front
        ((cx, bbox.min_y, cz), (0, -1, 0), dx * dz),    # back
        ((bbox.max_x, cy, cz), (1, 0, 0), dy * dz),     # right
        ((bbox.min_x, cy, cz), (-1, 0, 0), dy * dz),    # left
    ]
    refs: list[SubshapeRef] = []
    for idx, (centroid, normal, area) in enumerate(face_defs):
        fid = f"{shape_id}:face:{idx}"
        tags = _auto_tags_for_normal(normal)
        refs.append(
            SubshapeRef(
                id=fid,
                kind=SubshapeKind.FACE,
                index=idx,
                centroid=centroid,
                normal=normal,
                area=area,
                tags=tags,
            )
        )
    return refs


def synthetic_cylinder_faces(shape_id: str, bbox: BoundingBox) -> list[SubshapeRef]:
    cx = (bbox.min_x + bbox.max_x) / 2
    cy = (bbox.min_y + bbox.max_y) / 2
    r = (bbox.max_x - bbox.min_x) / 2
    h = bbox.max_z - bbox.min_z
    top_area = math.pi * r * r
    lat_area = 2 * math.pi * r * h
    return [
        SubshapeRef(id=f"{shape_id}:face:0", kind=SubshapeKind.FACE, index=0,
                    centroid=(cx, cy, bbox.max_z), normal=(0, 0, 1), area=top_area,
                    tags=["top", "+Z"]),
        SubshapeRef(id=f"{shape_id}:face:1", kind=SubshapeKind.FACE, index=1,
                    centroid=(cx, cy, bbox.min_z), normal=(0, 0, -1), area=top_area,
                    tags=["bottom", "-Z"]),
        SubshapeRef(id=f"{shape_id}:face:2", kind=SubshapeKind.FACE, index=2,
                    centroid=(cx, cy, (bbox.min_z + bbox.max_z) / 2), normal=None,
                    area=lat_area, tags=["lateral"]),
    ]


def synthetic_sphere_faces(shape_id: str, bbox: BoundingBox) -> list[SubshapeRef]:
    cx = (bbox.min_x + bbox.max_x) / 2
    cy = (bbox.min_y + bbox.max_y) / 2
    cz = (bbox.min_z + bbox.max_z) / 2
    r = (bbox.max_x - bbox.min_x) / 2
    return [
        SubshapeRef(id=f"{shape_id}:face:0", kind=SubshapeKind.FACE, index=0,
                    centroid=(cx, cy, cz), normal=None, area=4 * math.pi * r * r,
                    tags=["spherical"]),
    ]


def synthetic_faces(shape_id: str, kind: str, bbox: BoundingBox) -> list[SubshapeRef]:
    """Dispatch synthetic face generation based on shape kind."""
    if kind == "box":
        return synthetic_box_faces(shape_id, bbox)
    if kind == "cylinder":
        return synthetic_cylinder_faces(shape_id, bbox)
    if kind == "sphere":
        return synthetic_sphere_faces(shape_id, bbox)
    # Default: 6-face box-like approximation
    return synthetic_box_faces(shape_id, bbox)


def synthetic_edges(shape_id: str, edge_ids: list[str], bbox: BoundingBox) -> list[SubshapeRef]:
    """Generate synthetic edge refs from existing edge_ids list."""
    cx = (bbox.min_x + bbox.max_x) / 2
    cy = (bbox.min_y + bbox.max_y) / 2
    cz = (bbox.min_z + bbox.max_z) / 2
    refs: list[SubshapeRef] = []
    for idx, eid in enumerate(edge_ids):
        refs.append(
            SubshapeRef(
                id=eid,
                kind=SubshapeKind.EDGE,
                index=idx,
                centroid=(cx, cy, cz),
                length=None,
                tags=[],
            )
        )
    return refs


def build_synthetic_topology(shape_id: str, kind: str, bbox: BoundingBox,
                             edge_ids: list[str]) -> TopologyMap:
    return TopologyMap(
        shape_id=shape_id,
        faces=synthetic_faces(shape_id, kind, bbox),
        edges=synthetic_edges(shape_id, edge_ids, bbox),
    )


# ── Selector engine ─────────────────────────────────────────────────


def select(refs: list[SubshapeRef], query: SelectorQuery) -> list[SubshapeRef]:
    """Filter and sort subshape refs using a :class:`SelectorQuery`."""
    result = list(refs)

    # Filter by kind
    expected_kind = SubshapeKind.FACE if query.kind == "face" else SubshapeKind.EDGE
    result = [r for r in result if r.kind == expected_kind]

    # Filter by direction (cosine similarity to normal)
    if query.direction is not None:
        d = _vec_normalise(query.direction)
        filtered: list[SubshapeRef] = []
        for r in result:
            if r.normal is not None:
                n = _vec_normalise(r.normal)
                cos_sim = _vec_dot(d, n)
                if cos_sim >= 1.0 - query.direction_tolerance:
                    filtered.append(r)
        result = filtered

    # Filter by proximity to a point
    if query.near_point is not None:
        p = query.near_point
        tol = query.near_tolerance
        result = [
            r for r in result
            if math.sqrt(
                (r.centroid[0] - p[0]) ** 2
                + (r.centroid[1] - p[1]) ** 2
                + (r.centroid[2] - p[2]) ** 2
            )
            <= tol
        ]

    # Filter by area range
    if query.min_area is not None:
        result = [r for r in result if r.area is not None and r.area >= query.min_area]
    if query.max_area is not None:
        result = [r for r in result if r.area is not None and r.area <= query.max_area]

    # Filter by tags (all requested tags must be present)
    if query.tags:
        tag_set = set(query.tags)
        result = [r for r in result if tag_set.issubset(set(r.tags))]

    # Sort
    if query.sort_by:
        key_map = {
            "x": lambda r: r.centroid[0],
            "y": lambda r: r.centroid[1],
            "z": lambda r: r.centroid[2],
            "area": lambda r: r.area or 0.0,
            "length": lambda r: r.length or 0.0,
        }
        key_fn = key_map.get(query.sort_by)
        if key_fn:
            result.sort(key=key_fn, reverse=query.sort_reverse)

    # Limit
    if query.limit is not None:
        result = result[: query.limit]

    return result
