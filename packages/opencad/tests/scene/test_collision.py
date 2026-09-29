import json
from pathlib import Path

import pytest

from opencad import AssemblyTree, AssemblyComponent, RigidTransform
from opencad.scene import (
    Interaction,
    SceneCollider,
    SceneDocument,
    SceneEntity,
    SceneInterface,
    SceneState,
    evaluate_scene,
    validate_scene_motion,
)

EXAMPLES = Path(__file__).resolve().parents[3] / "opencad-viewport/src/examples"


def entity(id, position=(0, 0, 0), size=(2, 2, 2)):
    return SceneEntity(
        id=id,
        name=id,
        transform=RigidTransform(translation_mm=position),
        assembly=AssemblyTree(
            id=id,
            name=id,
            root_ids=[id],
            components={id: AssemblyComponent(id=id, name=id, geometry_refs=[id])},
        ),
        colliders=[SceneCollider(id=id + "-body", component_id=id, size_mm=size)],
    )


def crossing(duration=1, obstacle_x=0):
    return SceneDocument(
        id="cross",
        name="Crossing",
        entities={
            "arm": entity("arm", (-10, 0, 0), (1, 1, 1)),
            "obstacle": entity("obstacle", (obstacle_x, 0, 0), (0.01, 2, 2)),
        },
        interactions=[
            Interaction(
                id="move",
                actor_id="arm",
                target_id="obstacle",
                interaction_type="MOVE",
                duration_s=duration,
                actor_pose=RigidTransform(translation_mm=(10, 0, 0)),
            )
        ],
    )


def test_fast_thin_obstacle_crossing_is_not_skipped_between_clear_endpoints():
    doc = crossing(0.001)
    assert validate_scene_motion(doc, 0, 0).status == "clear"
    assert validate_scene_motion(doc, 0.001, 0.001).status == "clear"
    report = validate_scene_motion(doc, time_tolerance_s=1e-8)
    assert report.status in ("collision", "uncertain")
    assert 0 < report.safe_time_s < 0.0005
    assert set(report.collider_ids) == {"arm-body", "obstacle-body"}
    assert (
        validate_scene_motion(doc, 0, report.safe_time_s, time_tolerance_s=1e-8).status
        == "clear"
    )


def test_precision_exhaustion_fails_closed():
    report = validate_scene_motion(crossing(obstacle_x=-7.543), max_depth=1)
    assert report.status == "uncertain"
    assert report.safe_time_s == 0


def test_surface_contact_can_slide_but_penetration_is_rejected():
    doc = SceneDocument(
        id="contact",
        name="Contact",
        entities={"a": entity("a"), "b": entity("b", (2, 0, 0))},
        interactions=[
            Interaction(
                id="slide",
                actor_id="b",
                target_id="a",
                interaction_type="MOVE",
                duration_s=1,
                actor_pose=RigidTransform(translation_mm=(2, 4, 0)),
            )
        ],
    )
    assert validate_scene_motion(doc).status == "clear"
    raw = doc.model_dump()
    raw["entities"]["b"]["transform"]["translation_mm"] = (1.9, 0, 0)
    assert (
        validate_scene_motion(SceneDocument.model_validate(raw)).status == "collision"
    )


def test_rotating_chain_with_identical_endpoint_poses_still_checks_the_sweep():
    arm = entity("arm", (0, 0, 0), (1, 1, 1))
    arm.assembly.components["root"] = AssemblyComponent(
        id="root", name="root", child_ids=["arm"]
    )
    arm.assembly.root_ids = ["root"]
    arm.colliders[0].transform = RigidTransform(translation_mm=(5, 0, 0))
    half_turn = RigidTransform(rotation_quaternion_xyzw=(0, 0, 1, 0))
    doc = SceneDocument(
        id="spin",
        name="Spin",
        entities={"arm": arm, "obstacle": entity("obstacle", (-5, 0, 0))},
        interactions=[
            Interaction(
                id="spin",
                actor_id="arm",
                target_id="obstacle",
                interaction_type="MOVE",
                duration_s=1,
                component_poses={"root": half_turn, "arm": half_turn},
            )
        ],
    )
    assert validate_scene_motion(doc, 0, 0).status == "clear"
    assert validate_scene_motion(doc, 1, 1).status == "clear"
    assert validate_scene_motion(doc).status in ("collision", "uncertain")


def test_attached_payload_is_checked_even_when_gripper_clears_obstacle():
    arm = entity("arm", (-6, 0, 3), (0.2, 0.2, 0.2))
    arm.interfaces["grip"] = SceneInterface(
        id="grip",
        component_id="arm",
        transform=RigidTransform(translation_mm=(0, 0, -3)),
    )
    doc = SceneDocument(
        id="payload",
        name="Payload",
        entities={
            "arm": arm,
            "box": entity("box", (-6, 0, 0)),
            "obstacle": entity("obstacle"),
        },
        interactions=[
            Interaction(
                id="grasp",
                actor_id="arm",
                target_id="box",
                interaction_type="GRASP",
                actor_interface="grip",
            ),
            Interaction(
                id="carry",
                actor_id="arm",
                target_id="box",
                interaction_type="MOVE",
                duration_s=1,
                actor_pose=RigidTransform(translation_mm=(6, 0, 3)),
            ),
        ],
    )
    report = validate_scene_motion(doc)
    assert report.status in ("collision", "uncertain")
    assert set(report.collider_ids) == {"box-body", "obstacle-body"}


def test_checks_self_collision_ground_and_explicit_exclusions():
    arm = entity("arm")
    arm.assembly.components["child"] = AssemblyComponent(
        id="child", name="child", geometry_refs=["child"]
    )
    arm.assembly.components["arm"].child_ids = ["child"]
    arm.colliders.append(
        SceneCollider(id="child-body", component_id="child", size_mm=(2, 2, 2))
    )
    doc = SceneDocument(id="self", name="self", entities={"arm": arm})
    assert validate_scene_motion(doc).status == "collision"
    doc.collision_exclusions = [("arm-body", "child-body")]
    assert validate_scene_motion(doc).status == "clear"
    doc.ground_z_mm = 0
    assert "$ground" in validate_scene_motion(doc).collider_ids


def test_missing_collider_coverage_is_not_a_clearance_guarantee():
    doc = crossing()
    doc.entities["arm"].colliders = []
    report = validate_scene_motion(doc)
    assert report.status == "unchecked"
    assert report.unchecked_components == ["arm/arm"]


def test_corrected_demo_has_complete_coverage_and_no_exclusions(
    assert_scene_state_matches,
):
    doc = SceneDocument.model_validate(
        json.loads((EXAMPLES / "robotPickPlace.json").read_text())["document"]
    )
    assert doc.collision_exclusions == []
    report = validate_scene_motion(doc)
    assert report.status == "clear" and report.safe_time_s == 12
    assert report.unchecked_components == []
    for sample in json.loads((EXAMPLES / "robotPickPlace.states.json").read_text()):
        assert_scene_state_matches(
            evaluate_scene(doc, sample["time_s"]), SceneState.model_validate(sample)
        )
    final = evaluate_scene(doc, 12)
    assert final.entity_transforms["box"].translation_mm == pytest.approx((0, 24, 8))
    assert final.attachments == {} and final.placements == {"box": "table"}


def test_original_unsafe_gripper_approach_is_detected():
    data = json.loads((EXAMPLES / "robotPickPlaceLegacy.json").read_text())
    doc = SceneDocument.model_validate(data["document"])
    # Focus the regression on the observed gripper/box pair; legacy joint
    # placeholders also overlap, so other components intentionally lack coverage.
    for name, eid in [("gripper", "arm"), ("box", "box")]:
        mesh = next(m for m in data["meshes"] if m["shapeId"] == name)
        for index in range(0, len(mesh["vertices"]), 24):
            vertices = mesh["vertices"][index : index + 24]
            low = [min(vertices[i::3]) for i in range(3)]
            high = [max(vertices[i::3]) for i in range(3)]
            doc.entities[eid].colliders.append(
                SceneCollider(
                    id=f"{name}-{index}",
                    component_id=name,
                    size_mm=tuple(b - a for a, b in zip(low, high)),
                    transform=RigidTransform(
                        translation_mm=tuple((a + b) / 2 for a, b in zip(low, high))
                    ),
                )
            )
    report = validate_scene_motion(doc)
    assert report.status in ("collision", "uncertain")
    assert 1.3 < report.safe_time_s < 1.5
    assert set(report.shape_ids) == {"gripper", "box"}


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["entities"]["arm"]["colliders"][0].update(size_mm=[0, 1, 1]),
        lambda d: d["entities"]["arm"]["colliders"][0].update(component_id="missing"),
        lambda d: d["entities"]["arm"]["colliders"][0].update(id="obstacle-body"),
        lambda d: d.update(collision_exclusions=[["missing", "arm-body"]]),
    ],
)
def test_invalid_collision_contract_is_rejected(change):
    raw = crossing().model_dump()
    change(raw)
    with pytest.raises(ValueError):
        SceneDocument.model_validate(raw)
