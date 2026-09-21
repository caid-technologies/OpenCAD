from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from opencad.gears import SpurGearSpec, spur_gear
from opencad.kinematics import GearCoupling, evaluate_assembly_pose, joint_value_at_progress, resolve_gear_progress
from opencad.kernel.core.models import KinematicJoint


def pair():
    return [
        KinematicJoint(id="a", type="revolute", parent_shape_id="frame", child_shape_id="a-shape", origin_mm=(-30, 0, 0), lower_limit=0, upper_limit=2 * math.tau),
        KinematicJoint(id="b", type="revolute", parent_shape_id="frame", child_shape_id="b-shape", origin_mm=(30, 0, 0), lower_limit=-math.tau, upper_limit=0),
    ]


def coupling(**overrides):
    return GearCoupling(**{"driver_joint_id": "a", "driven_joint_id": "b", "driver_teeth": 20, "driven_teeth": 40, **overrides})


@pytest.mark.parametrize("t", [0, .03125, .125, .25, .375, .5, .75, 1])
def test_gears_are_synchronized_about_stationary_centers(t):
    joints = pair()
    resolved = resolve_gear_progress(joints, {"a": t}, [coupling()])
    angles = [joint_value_at_progress(j, resolved[j.id]) for j in joints]
    assert angles[0] == pytest.approx(2 * math.tau * t)
    assert angles[1] == pytest.approx(-math.tau * t)
    transforms = evaluate_assembly_pose(joints, {"a": t}, gear_couplings=[coupling()])
    for joint, angle in zip(joints, angles):
        transform = transforms[joint.child_shape_id]
        x, y, z = joint.origin_mm
        dx, dy, dz = transform.translation_mm
        assert (math.cos(angle) * x - math.sin(angle) * y + dx,
                math.sin(angle) * x + math.cos(angle) * y + dy, z + dz) == pytest.approx((x, y, z))


def test_invalid_couplings_fail_instead_of_silently_clamping():
    joints = pair()
    for bad in [coupling(driver_joint_id="missing"), coupling(driven_joint_id="a"), coupling(driven_teeth=10)]:
        with pytest.raises(ValueError):
            evaluate_assembly_pose(joints, {"a": 1}, gear_couplings=[bad])
    with pytest.raises(ValueError, match="cycle"):
        resolve_gear_progress(joints, {}, [coupling(), coupling(driver_joint_id="b", driven_joint_id="a")])
    with pytest.raises(ValueError, match="conflicts"):
        resolve_gear_progress(joints, {"a": .25, "b": .25}, [coupling()])
    with pytest.raises(ValueError, match="distinct driver"):
        resolve_gear_progress(joints, {}, [coupling(), coupling()])
    with pytest.raises(ValueError, match="parallel"):
        resolve_gear_progress([joints[0], joints[1].model_copy(update={"axis": (1, 0, 0)})], {}, [coupling()])
    with pytest.raises(ValidationError):
        coupling(driver_teeth=0)
    with pytest.raises(ValidationError):
        coupling(phase_radians=float("nan"))


@pytest.mark.parametrize("values", [{"teeth": 4}, {"teeth": 20.5}, {"bore_diameter_mm": 40}, {"backlash_mm": 1}, {"module_mm": float("inf")}])
def test_invalid_gear_profiles_are_rejected(values):
    with pytest.raises(ValidationError):
        SpurGearSpec(**values)


def test_native_gear_pair_has_clearance_through_a_tooth_cycle():
    cq = pytest.importorskip("cadquery")
    from opencad.kernel.core.backend_factory import create_backend
    from opencad.runtime import RuntimeContext

    context = RuntimeContext(backend=create_backend("occt", require_native=True))
    a = spur_gear(SpurGearSpec(teeth=20), center_mm=(-30, 0, 0), context=context)
    b = spur_gear(SpurGearSpec(teeth=40), center_mm=(30, 0, 0), phase_radians=math.pi - math.pi / 40, context=context)
    native_a = cq.Shape(context.kernel.get_native_shape(a.shape_id))
    native_b = cq.Shape(context.kernel.get_native_shape(b.shape_id))
    assert a.shape_id != b.shape_id
    for solid in (native_a, native_b):
        assert solid.isValid()
        assert len(solid.Solids()) == 1
        assert solid.Volume() > 1000
    # Check intermediate phases of one 18-degree driver tooth cycle. Periodic
    # tooth geometry repeats this contact configuration over the full turn.
    for degrees in [0, 3, 6, 9, 12, 15, 18]:
        moved_a = native_a.rotate((-30, 0, 0), (-30, 0, 1), degrees)
        moved_b = native_b.rotate((30, 0, 0), (30, 0, 1), -degrees / 2)
        assert moved_a.intersect(moved_b).Volume() < 1e-6
