from __future__ import annotations

import math

import pytest

from opencad.kinematics import (
    compose_transforms,
    evaluate_assembly_pose,
    evaluate_joint_pose,
    joint_value_at_progress,
)
from opencad.kernel.core.models import (
    JointUnit,
    KinematicJoint,
    KinematicJointType,
    RigidTransform,
)


def joint(**overrides) -> KinematicJoint:
    payload = {
        "id": "joint-1",
        "type": KinematicJointType.REVOLUTE,
        "parent_shape_id": "base",
        "child_shape_id": "lid",
        "axis": (0.0, 0.0, 1.0),
        "origin_mm": (10.0, 0.0, 0.0),
        "lower_limit": 0.0,
        "upper_limit": math.pi / 2.0,
        **overrides,
    }
    return KinematicJoint(**payload)


def assert_vector_close(actual, expected, tolerance=1e-9):
    assert len(actual) == len(expected)
    for value, target in zip(actual, expected):
        assert value == pytest.approx(target, abs=tolerance)


def test_revolute_pose_contains_pivot_offset_and_quaternion():
    pose = evaluate_joint_pose(joint(), 1.0)

    assert pose.unit == JointUnit.RADIAN
    assert pose.value == pytest.approx(math.pi / 2.0)
    assert_vector_close(pose.transform.translation_mm, (10.0, -10.0, 0.0))
    assert_vector_close(
        pose.transform.rotation_quaternion_xyzw,
        (0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)),
    )


def test_prismatic_pose_translates_along_normalized_axis():
    pose = evaluate_joint_pose(
        joint(
            type=KinematicJointType.PRISMATIC,
            axis=(2.0, 0.0, 0.0),
            origin_mm=(0.0, 0.0, 0.0),
            lower_limit=-2.0,
            upper_limit=8.0,
        ),
        0.5,
    )

    assert pose.unit == JointUnit.MILLIMETER
    assert pose.value == pytest.approx(3.0)
    assert_vector_close(pose.transform.translation_mm, (3.0, 0.0, 0.0))
    assert pose.transform.rotation_quaternion_xyzw == (0.0, 0.0, 0.0, 1.0)


def test_fixed_joint_is_identity():
    pose = evaluate_joint_pose(
        joint(
            type=KinematicJointType.FIXED,
            lower_limit=0.0,
            upper_limit=0.0,
        ),
        0.75,
    )

    assert pose.unit == JointUnit.NONE
    assert pose.transform == RigidTransform.identity()


def test_joint_progress_clamps_for_pure_evaluator():
    model = joint(lower_limit=-1.0, upper_limit=1.0)
    assert joint_value_at_progress(model, -5.0) == pytest.approx(-1.0)
    assert joint_value_at_progress(model, 5.0) == pytest.approx(1.0)


def test_assembly_pose_composes_parent_and_child_joints():
    root_hinge = joint(
        id="root-hinge",
        parent_shape_id="base",
        child_shape_id="arm",
        origin_mm=(0.0, 0.0, 0.0),
        lower_limit=0.0,
        upper_limit=math.pi / 2.0,
    )
    slider = joint(
        id="slider",
        type=KinematicJointType.PRISMATIC,
        parent_shape_id="arm",
        child_shape_id="tool",
        axis=(1.0, 0.0, 0.0),
        origin_mm=(0.0, 0.0, 0.0),
        lower_limit=0.0,
        upper_limit=10.0,
    )

    transforms = evaluate_assembly_pose(
        [root_hinge, slider],
        {"root-hinge": 1.0, "slider": 1.0},
    )

    assert_vector_close(transforms["tool"].translation_mm, (0.0, 10.0, 0.0))
    assert_vector_close(
        transforms["tool"].rotation_quaternion_xyzw,
        transforms["arm"].rotation_quaternion_xyzw,
    )


def test_assembly_pose_rejects_two_parents_for_one_child():
    first = joint(id="a", child_shape_id="shared")
    second = joint(id="b", parent_shape_id="other", child_shape_id="shared")

    with pytest.raises(ValueError, match="more than one parent"):
        evaluate_assembly_pose([first, second])


def test_transform_composition_rotates_child_translation():
    quarter_turn = evaluate_joint_pose(
        joint(origin_mm=(0.0, 0.0, 0.0)),
        1.0,
    ).transform
    translated = RigidTransform(
        translation_mm=(10.0, 0.0, 0.0),
        rotation_quaternion_xyzw=(0.0, 0.0, 0.0, 1.0),
    )

    combined = compose_transforms(quarter_turn, translated)
    assert_vector_close(combined.translation_mm, (0.0, 10.0, 0.0))
