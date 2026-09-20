from __future__ import annotations

import math

import pytest

from opencad.kinematics import (
    compose_transforms,
    evaluate_assembly_pose,
    evaluate_joint_pose,
    joint_value_at_progress,
)
from opencad.kernel.core.errors import Failure
from opencad.kernel.core.models import (
    JointUnit,
    KinematicJoint,
    KinematicJointType,
    RigidTransform,
    Success,
)
from opencad.kernel.operations.handlers import OpenCadKernel
from opencad.kernel.operations.registry import OperationRegistry
from opencad.kernel.operations.schemas import (
    CreateBoxInput,
    CreateKinematicJointInput,
    EvaluateKinematicAssemblyInput,
    EvaluateKinematicJointInput,
    KinematicJointType as SchemaKinematicJointType,
    ListKinematicJointsInput,
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


def make_kernel() -> OpenCadKernel:
    return OpenCadKernel(tolerance=1e-6, id_strategy="readable")


def test_kernel_creates_lists_and_evaluates_revolute_joint():
    kernel = make_kernel()
    base = kernel.create_box(CreateBoxInput(length=20, width=20, height=5))
    lid = kernel.create_box(CreateBoxInput(length=20, width=20, height=2))
    assert isinstance(base, Success) and isinstance(lid, Success)

    created = kernel.create_kinematic_joint(
        CreateKinematicJointInput(
            type=SchemaKinematicJointType.REVOLUTE,
            parent_shape_id=base.shape_id,
            child_shape_id=lid.shape_id,
            axis=(0, 0, 1),
            origin_mm=(10, 0, 0),
            lower_limit=0,
            upper_limit=math.pi / 2,
            label="Lid hinge",
        )
    )
    assert isinstance(created, Success)
    joint_id = created.metadata["joint_id"]
    assert created.metadata["joint"]["unit"] == "radian"

    listed = kernel.list_kinematic_joints(ListKinematicJointsInput())
    assert isinstance(listed, Success)
    assert [item["id"] for item in listed.metadata["joints"]] == [joint_id]

    evaluated = kernel.evaluate_kinematic_joint(
        EvaluateKinematicJointInput(joint_id=joint_id, progress=1.0)
    )
    assert isinstance(evaluated, Success)
    assert evaluated.metadata["pose"]["value"] == pytest.approx(math.pi / 2)
    assert evaluated.metadata["pose"]["child_shape_id"] == lid.shape_id


def test_kernel_rejects_second_parent_for_same_child():
    kernel = make_kernel()
    first_parent = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    second_parent = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    child = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    assert isinstance(first_parent, Success)
    assert isinstance(second_parent, Success)
    assert isinstance(child, Success)

    first = kernel.create_kinematic_joint(
        CreateKinematicJointInput(
            type=SchemaKinematicJointType.FIXED,
            parent_shape_id=first_parent.shape_id,
            child_shape_id=child.shape_id,
        )
    )
    assert isinstance(first, Success)

    second = kernel.create_kinematic_joint(
        CreateKinematicJointInput(
            type=SchemaKinematicJointType.FIXED,
            parent_shape_id=second_parent.shape_id,
            child_shape_id=child.shape_id,
        )
    )
    assert isinstance(second, Failure)
    assert second.code.value == "JOINT_DUPLICATE_CHILD"


def test_kernel_rejects_kinematic_cycles():
    kernel = make_kernel()
    base = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    arm = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    tool = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    assert isinstance(base, Success) and isinstance(arm, Success) and isinstance(tool, Success)

    for parent, child in [
        (base.shape_id, arm.shape_id),
        (arm.shape_id, tool.shape_id),
    ]:
        result = kernel.create_kinematic_joint(
            CreateKinematicJointInput(
                type=SchemaKinematicJointType.REVOLUTE,
                parent_shape_id=parent,
                child_shape_id=child,
                upper_limit=1.0,
            )
        )
        assert isinstance(result, Success)

    cycle = kernel.create_kinematic_joint(
        CreateKinematicJointInput(
            type=SchemaKinematicJointType.REVOLUTE,
            parent_shape_id=tool.shape_id,
            child_shape_id=base.shape_id,
            upper_limit=1.0,
        )
    )
    assert isinstance(cycle, Failure)
    assert cycle.code.value == "JOINT_CYCLE"


def test_kernel_evaluates_full_joint_tree():
    kernel = make_kernel()
    base = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    arm = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    tool = kernel.create_box(CreateBoxInput(length=5, width=5, height=5))
    assert isinstance(base, Success) and isinstance(arm, Success) and isinstance(tool, Success)

    hinge = kernel.create_kinematic_joint(
        CreateKinematicJointInput(
            type=SchemaKinematicJointType.REVOLUTE,
            parent_shape_id=base.shape_id,
            child_shape_id=arm.shape_id,
            upper_limit=math.pi / 2,
        )
    )
    slider = kernel.create_kinematic_joint(
        CreateKinematicJointInput(
            type=SchemaKinematicJointType.PRISMATIC,
            parent_shape_id=arm.shape_id,
            child_shape_id=tool.shape_id,
            axis=(1, 0, 0),
            upper_limit=10,
        )
    )
    assert isinstance(hinge, Success) and isinstance(slider, Success)

    evaluated = kernel.evaluate_kinematic_assembly(
        EvaluateKinematicAssemblyInput(
            progress_by_joint={
                hinge.metadata["joint_id"]: 1.0,
                slider.metadata["joint_id"]: 1.0,
            }
        )
    )
    assert isinstance(evaluated, Success)
    transforms = evaluated.metadata["transforms"]
    assert set(transforms) == {arm.shape_id, tool.shape_id}
    assert_vector_close(transforms[tool.shape_id]["translation_mm"], (0.0, 10.0, 0.0))


def test_registry_exposes_kinematic_operations_and_schema():
    registry = OperationRegistry(make_kernel())
    expected = {
        "create_kinematic_joint",
        "delete_kinematic_joint",
        "list_kinematic_joints",
        "evaluate_kinematic_joint",
        "evaluate_kinematic_assembly",
    }
    assert expected <= set(registry.list_operations())
    assert registry.get_json_schema("create_kinematic_joint")["properties"]
