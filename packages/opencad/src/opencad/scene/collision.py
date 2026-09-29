"""Conservative continuous validation of authored motion using oriented boxes.

SAT separates boxes at an interval midpoint. A bound on projected point travel
certifies the *whole* interval, including rotation and nested attachments. Any
uncertified interval is subdivided; exhausted precision fails closed. This is a
kinematic guard over authored colliders, not a mesh/physics or planning engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from opencad.kernel.core.models import RigidTransform
from opencad.kinematics import compose_transforms
from opencad.scene.models import SceneDocument
from opencad.scene.playback import evaluate_scene, interpolate_transform, scene_duration


class MotionCheck(BaseModel):
    status: Literal["clear", "collision", "uncertain", "unchecked"]
    safe_time_s: float
    time_s: float
    collider_ids: list[str] = Field(default_factory=list)
    shape_ids: list[str] = Field(default_factory=list)
    unchecked_components: list[str] = Field(default_factory=list)


@dataclass
class _Link:
    key: tuple[str, ...]
    start: RigidTransform
    end: RigidTransform


@dataclass
class _Box:
    id: str
    entity: str
    component: str
    half: np.ndarray
    links: list[_Link]
    shapes: list[str]


def _rotation(pose: RigidTransform) -> np.ndarray:
    q = np.array(pose.rotation_quaternion_xyzw, dtype=float)
    length = np.linalg.norm(q)
    q = q / length if length > 1e-12 else np.array([0.0, 0.0, 0.0, 1.0])
    x, y, z, w = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def _angular(link: _Link) -> tuple[float, np.ndarray]:
    # Relative rotation axis in the parent frame; shortest-path SLERP.
    def unit(q):
        q = np.array(q, dtype=float)
        n = np.linalg.norm(q)
        return q / n if n > 1e-12 else np.array([0.0, 0.0, 0.0, 1.0])

    a, b = (
        unit(link.start.rotation_quaternion_xyzw),
        unit(link.end.rotation_quaternion_xyzw),
    )
    if a @ b < 0:
        b = -b
    xyz = a[3] * b[:3] - b[3] * a[:3] + np.cross(a[:3], b[:3])
    sine = np.linalg.norm(xyz)
    angle = 2 * math.atan2(sine, max(0.0, float(a @ b)))
    return angle, xyz / sine if sine > 0 else np.zeros(3)


def _world(links: list[_Link], progress: float):
    pose = RigidTransform.identity()
    for link in links:
        pose = compose_transforms(
            pose, interpolate_transform(link.start, link.end, progress)
        )
    return np.array(pose.translation_mm), _rotation(pose)


def _travel(links: list[_Link], half: np.ndarray, axis: np.ndarray) -> float:
    """Bound projected point travel per unit MOVE progress (duration independent)."""
    radii = [0.0] * (len(links) + 1)
    speeds = [0.0] * (len(links) + 1)
    radii[-1] = float(np.linalg.norm(half))
    angles = [_angular(link) for link in links]
    for i in range(len(links) - 1, -1, -1):
        link = links[i]
        a, b = np.array(link.start.translation_mm), np.array(link.end.translation_mm)
        radii[i] = radii[i + 1] + max(np.linalg.norm(a), np.linalg.norm(b))
        # Normalized lerp has peak angular speed 4*tan(angle/4);
        # use that bound for the small-angle interpolation branch.
        angle = angles[i][0]
        angular_bound = 4 * math.tan(angle / 4) if angle < 0.064 else angle
        speeds[i] = (
            speeds[i + 1] + float(np.linalg.norm(b - a)) + angular_bound * radii[i + 1]
        )

    def projected(i: int, n: np.ndarray) -> float:
        if i == len(links):
            return 0.0
        link = links[i]
        delta = np.array(link.end.translation_mm) - link.start.translation_mm
        angle, rotation_axis = angles[i]
        linear = abs(float(n @ delta))
        # A constant rotation, or rotation about the separating normal,
        # preserves that projection. This certifies sliding surface contact.
        if angle == 0 or np.linalg.norm(np.cross(rotation_axis, n)) == 0:
            return linear + projected(i + 1, _rotation(link.start).T @ n)
        angular_bound = 4 * math.tan(angle / 4) if angle < 0.064 else angle
        return linear + angular_bound * radii[i + 1] + speeds[i + 1]

    return projected(0, axis)


def _paths(document: SceneDocument, time: float, action=None) -> list[_Box]:
    state = evaluate_scene(document, time)

    def fixed(key, pose):
        return _Link(key, pose, pose)

    def components(eid, cid):
        entity = document.entities[eid]
        parents = {
            child: c.id
            for c in entity.assembly.components.values()
            for child in c.child_ids
        }
        lineage = [cid]
        while lineage[-1] in parents:
            lineage.append(parents[lineage[-1]])
        return [
            _Link(
                ("component", eid, key),
                state.component_transforms[eid][key],
                action.component_poses.get(key, state.component_transforms[eid][key])
                if action is not None and action.actor_id == eid
                else state.component_transforms[eid][key],
            )
            for key in reversed(lineage)
        ]

    def entity_path(eid):
        attachment = state.attachments.get(eid)
        if attachment:
            actor = attachment.actor_id
            interface = document.entities[actor].interfaces[attachment.actor_interface]
            return (
                entity_path(actor)
                + components(actor, interface.component_id)
                + [
                    fixed(("interface", actor, interface.id), interface.transform),
                    fixed(("attachment", eid), attachment.relative_transform),
                ]
            )
        pose = state.entity_transforms[eid]
        end = (
            action.actor_pose
            if action is not None
            and action.actor_id == eid
            and action.actor_pose is not None
            else pose
        )
        return [_Link(("entity", eid), pose, end)]

    boxes = []
    for eid, entity in document.entities.items():
        for collider in entity.colliders:
            boxes.append(
                _Box(
                    collider.id,
                    eid,
                    collider.component_id,
                    np.array(collider.size_mm) / 2,
                    entity_path(eid)
                    + components(eid, collider.component_id)
                    + [fixed(("collider", collider.id), collider.transform)],
                    entity.assembly.components[collider.component_id].geometry_refs,
                )
            )
    return boxes


def _pair_check(
    a: _Box,
    b: _Box | None,
    low: float,
    high: float,
    tolerance: float,
    ground: float | None,
    progress_tolerance: float,
    max_depth: int,
):
    left, right = a.links, b.links if b else []
    # Shared motion can be cancelled exactly, even when an object is attached.
    if b:
        common = 0
        while (
            common < min(len(left), len(right))
            and left[common].key == right[common].key
        ):
            common += 1
        left, right = left[common:], right[common:]

    def measure(progress):
        ca, ra = _world(left, progress)
        if b is None:
            return [
                (
                    float(ca[2] - np.abs(ra[2]) @ a.half - ground),
                    np.array([0.0, 0.0, 1.0]),
                )
            ]
        cb, rb = _world(right, progress)
        axes = [*ra.T, *rb.T, *(np.cross(x, y) for x in ra.T for y in rb.T)]
        result = []
        for axis in axes:
            length = np.linalg.norm(axis)
            if length < 1e-10:
                continue
            axis = axis / length
            gap = (
                abs(float((cb - ca) @ axis))
                - np.abs(ra.T @ axis) @ a.half
                - np.abs(rb.T @ axis) @ b.half
            )
            result.append((float(gap), axis))
        return result

    def visit(lo, hi, depth):
        mid = (lo + hi) / 2
        gaps = measure(mid)
        for gap, axis in gaps:
            movement = (
                (
                    _travel(left, a.half, axis)
                    + (_travel(right, b.half, axis) if b else 0)
                )
                * (hi - lo)
                / 2
            )
            if gap + tolerance >= movement + 1e-12:
                return None
        penetrating = max(gap for gap, _ in gaps) < -tolerance
        if hi - lo <= progress_tolerance or depth >= max_depth:
            # At exact boundaries a known penetration may precede this interval.
            at_start = max(gap for gap, _ in measure(lo)) < -tolerance
            at_end = max(gap for gap, _ in measure(hi)) < -tolerance
            hit = lo if at_start else mid if penetrating else hi
            return (
                lo,
                hit,
                "collision" if penetrating or at_start or at_end else "uncertain",
            )
        return visit(lo, mid, depth + 1) or visit(mid, hi, depth + 1)

    return visit(low, high, 0)


def validate_scene_motion(
    document: SceneDocument,
    start_s: float = 0,
    end_s: float | None = None,
    *,
    tolerance_mm: float = 0.001,
    time_tolerance_s: float = 0.0001,
    max_depth: int = 20,
) -> MotionCheck:
    """Certify an interval or return the last certified time and offending pair.

    Results concern authored box colliders only. Missing collider coverage is
    reported as unchecked, never clear. Surface contact within tolerance is OK;
    grasp/placement do not exempt penetration. Explicit exclusions are honored.
    """
    end = scene_duration(document) if end_s is None else end_s
    if (
        not all(
            math.isfinite(x) for x in (start_s, end, tolerance_mm, time_tolerance_s)
        )
        or start_s < 0
        or end < start_s
        or tolerance_mm < 0
        or time_tolerance_s <= 0
        or not isinstance(max_depth, int)
        or isinstance(max_depth, bool)
        or not 1 <= max_depth <= 30
    ):
        raise ValueError("Invalid motion validation interval or tolerance.")
    end = min(end, scene_duration(document))
    start = min(start_s, end)
    missing = [
        f"{eid}/{cid}"
        for eid, e in document.entities.items()
        for cid, c in e.assembly.components.items()
        if c.geometry_refs and not any(x.component_id == cid for x in e.colliders)
    ]
    ignored = {frozenset(pair) for pair in document.collision_exclusions}
    segments = []
    elapsed = 0.0
    for action in document.interactions:
        if action.interaction_type == "MOVE":
            if elapsed <= end and elapsed + action.duration_s >= start:
                segments.append(
                    (
                        elapsed,
                        action.duration_s,
                        action,
                        max(start, elapsed),
                        min(end, elapsed + action.duration_s),
                    )
                )
            elapsed += action.duration_s
    if not segments:
        segments = [(start, 1.0, None, start, end)]
    for origin, duration, action, lo, hi in segments:
        boxes = _paths(document, origin, action)
        pairs = [
            (a, b)
            for a, b in combinations(boxes, 2)
            if (a.entity, a.component) != (b.entity, b.component)
            and frozenset((a.id, b.id)) not in ignored
        ]
        if document.ground_z_mm is not None:
            pairs += [(a, None) for a in boxes]
        first = None
        for a, b in pairs:
            result = _pair_check(
                a,
                b,
                (lo - origin) / duration,
                (hi - origin) / duration,
                tolerance_mm,
                document.ground_z_mm,
                time_tolerance_s / duration,
                max_depth,
            )
            if result is not None and (first is None or result[0] < first[0][0]):
                first = (result, a, b)
        if first:
            (safe, hit, status), a, b = first
            return MotionCheck(
                status=status,
                safe_time_s=origin + safe * duration,
                time_s=origin + hit * duration,
                collider_ids=[a.id, b.id if b else "$ground"],
                shape_ids=list(dict.fromkeys(a.shapes + (b.shapes if b else []))),
                unchecked_components=missing,
            )
    return MotionCheck(
        status="unchecked"
        if missing or not any(e.colliders for e in document.entities.values())
        else "clear",
        safe_time_s=end,
        time_s=end,
        unchecked_components=missing,
    )
