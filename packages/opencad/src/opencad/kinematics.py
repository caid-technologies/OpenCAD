from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from opencad.kernel.core.models import (
    JointPose,
    KinematicJoint,
    KinematicJointType,
    RigidTransform,
)


def clamp_progress(progress: float) -> float:
    """Clamp normalized joint progress into the closed [0, 1] interval."""
    if not math.isfinite(progress):
        raise ValueError("Joint progress must be finite.")
    return min(1.0, max(0.0, float(progress)))


def joint_value_at_progress(joint: KinematicJoint, progress: float) -> float:
    t = clamp_progress(progress)
    return joint.lower_limit + (joint.upper_limit - joint.lower_limit) * t


def evaluate_joint_pose(joint: KinematicJoint, progress: float) -> JointPose:
    """Evaluate one rigid joint into a renderer-ready transform.

    The returned transform acts on the child shape in the parent coordinate
    frame. Revolute joints include the pivot-offset translation
    origin minus rotated-origin so consumers can apply translation plus
    quaternion directly to the child mesh without knowing joint semantics.
    """
    t = clamp_progress(progress)
    value = joint_value_at_progress(joint, t)

    if joint.type == KinematicJointType.FIXED:
        transform = RigidTransform.identity()
    elif joint.type == KinematicJointType.PRISMATIC:
        axis = _unit(joint.axis)
        transform = RigidTransform(
            translation_mm=tuple(component * value for component in axis),
            rotation_quaternion_xyzw=(0.0, 0.0, 0.0, 1.0),
        )
    else:
        axis = _unit(joint.axis)
        quaternion = _axis_angle_quaternion(axis, value)
        rotated_origin = _rotate_vector(quaternion, joint.origin_mm)
        transform = RigidTransform(
            translation_mm=tuple(
                joint.origin_mm[index] - rotated_origin[index]
                for index in range(3)
            ),
            rotation_quaternion_xyzw=quaternion,
        )

    return JointPose(
        joint_id=joint.id,
        child_shape_id=joint.child_shape_id,
        progress=t,
        value=value,
        unit=joint.unit,
        transform=transform,
    )


def evaluate_assembly_pose(
    joints: Sequence[KinematicJoint],
    progress_by_joint: Mapping[str, float] | None = None,
) -> dict[str, RigidTransform]:
    """Evaluate a tree of rigid joints into world transforms by child shape.

    Shapes that are only roots do not need an entry because identity is
    implied. Each child may have at most one parent joint. Cycles are rejected.
    """
    progress_by_joint = progress_by_joint or {}
    by_child: dict[str, KinematicJoint] = {}
    by_parent: dict[str, list[KinematicJoint]] = {}

    for joint in joints:
        if joint.child_shape_id in by_child:
            raise ValueError(
                f"Shape '{joint.child_shape_id}' has more than one parent kinematic joint."
            )
        by_child[joint.child_shape_id] = joint
        by_parent.setdefault(joint.parent_shape_id, []).append(joint)

    transforms: dict[str, RigidTransform] = {}
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(parent_shape_id: str, parent_transform: RigidTransform) -> None:
        if parent_shape_id in visiting:
            raise ValueError("Kinematic joint graph contains a cycle.")
        if parent_shape_id in visited:
            return
        visiting.add(parent_shape_id)

        for joint in by_parent.get(parent_shape_id, []):
            progress = progress_by_joint.get(joint.id, 0.0)
            local = evaluate_joint_pose(joint, progress).transform
            world = compose_transforms(parent_transform, local)
            transforms[joint.child_shape_id] = world
            walk(joint.child_shape_id, world)

        visiting.remove(parent_shape_id)
        visited.add(parent_shape_id)

    roots = sorted(
        {
            joint.parent_shape_id
            for joint in joints
            if joint.parent_shape_id not in by_child
        }
    )
    if joints and not roots:
        raise ValueError("Kinematic joint graph contains a cycle.")

    identity = RigidTransform.identity()
    for root in roots:
        walk(root, identity)

    if len(transforms) != len(joints):
        raise ValueError("Kinematic joint graph is disconnected or cyclic.")

    return transforms


def compose_transforms(parent: RigidTransform, child: RigidTransform) -> RigidTransform:
    """Compose rigid transforms using XYZW quaternions."""
    parent_q = _normalize_quaternion(parent.rotation_quaternion_xyzw)
    child_q = _normalize_quaternion(child.rotation_quaternion_xyzw)
    rotated_child_translation = _rotate_vector(parent_q, child.translation_mm)
    translation = tuple(
        parent.translation_mm[index] + rotated_child_translation[index]
        for index in range(3)
    )
    return RigidTransform(
        translation_mm=translation,
        rotation_quaternion_xyzw=_quaternion_multiply(parent_q, child_q),
    )


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-12:
        raise ValueError("Kinematic joint axis must be non-zero.")
    return tuple(component / length for component in vector)


def _axis_angle_quaternion(
    axis: tuple[float, float, float],
    angle_radians: float,
) -> tuple[float, float, float, float]:
    half = angle_radians / 2.0
    sine = math.sin(half)
    return _normalize_quaternion(
        (axis[0] * sine, axis[1] * sine, axis[2] * sine, math.cos(half))
    )


def _normalize_quaternion(
    quaternion: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    length = math.sqrt(sum(component * component for component in quaternion))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(component / length for component in quaternion)


def _quaternion_multiply(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return _normalize_quaternion(
        (
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
            lw * rw - lx * rx - ly * ry - lz * rz,
        )
    )


def _rotate_vector(
    quaternion: tuple[float, float, float, float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    qx, qy, qz, qw = _normalize_quaternion(quaternion)
    vx, vy, vz = vector

    # Optimized q * v * q^-1.
    tx = 2.0 * (qy * vz - qz * vy)
    ty = 2.0 * (qz * vx - qx * vz)
    tz = 2.0 * (qx * vy - qy * vx)
    return (
        vx + qw * tx + (qy * tz - qz * ty),
        vy + qw * ty + (qz * tx - qx * tz),
        vz + qw * tz + (qx * ty - qy * tx),
    )
