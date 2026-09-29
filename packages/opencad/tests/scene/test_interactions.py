from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from opencad import deserialize_scene, evaluate_scene, serialize_scene
from opencad.scene import Interaction, SceneDocument, SceneState

EXAMPLES = Path(__file__).resolve().parents[3] / "opencad-viewport/src/examples"


@pytest.fixture
def document():
    return SceneDocument.model_validate(
        json.loads((EXAMPLES / "robotPickPlaceLegacy.json").read_text())["document"]
    )


def test_pick_carry_place_and_return_preserves_independent_assemblies(document):
    before = document.model_dump_json()
    assert set(document.entities) == {"arm", "box", "table"}
    assert evaluate_scene(document, 1).entity_transforms["box"].translation_mm == (
        24,
        0,
        2,
    )
    grasp = evaluate_scene(document, 2)
    assert grasp.attachments["box"].actor_interface == "grip"
    assert grasp.entity_transforms["box"].translation_mm == (24, 0, 2)
    carry = evaluate_scene(document, 4)
    assert carry.entity_transforms["box"].translation_mm == pytest.approx(
        (24 / math.sqrt(2), 24 / math.sqrt(2), 10)
    )
    assert carry.entity_transforms["box"].rotation_quaternion_xyzw == pytest.approx(
        (0, 0, math.sin(math.pi / 8), math.cos(math.pi / 8))
    )
    for time in (6, 6.5, 7, 8, 9, 100):
        placed = evaluate_scene(document, time)
        assert placed.attachments == {}
        assert placed.placements == {"box": "table"}
        assert placed.entity_transforms["box"].translation_mm == pytest.approx(
            (0, 24, 8)
        )
    assert document.model_dump_json() == before
    assert evaluate_scene(document, 0).attachments == {}


def test_release_freezes_pose_without_support_record(document):
    raw = document.model_dump()
    raw["interactions"][5]["interaction_type"] = "RELEASE"
    raw["interactions"][5]["destination_id"] = None
    scene = SceneDocument.model_validate(raw)
    state = evaluate_scene(scene, 9)
    assert state.attachments == state.placements == {}
    assert state.entity_transforms["box"].translation_mm == pytest.approx((0, 24, 8))


def test_roundtrip_mid_grasp_restores_relationship_and_pose(document):
    document.time_s = 4
    restored = deserialize_scene(serialize_scene(document))
    assert evaluate_scene(restored) == evaluate_scene(document, 4)
    state = evaluate_scene(restored)
    assert SceneState.model_validate_json(state.model_dump_json()) == state


def test_grasp_offset_and_rotated_actor_frame(document):
    raw = document.model_dump()
    # The box is deliberately offset from the named interface when grasped.
    raw["entities"]["box"]["transform"]["translation_mm"] = [25, 1, 2]
    scene = SceneDocument.model_validate(raw)
    assert evaluate_scene(scene, 2).entity_transforms[
        "box"
    ].translation_mm == pytest.approx((25, 1, 2))
    assert evaluate_scene(scene, 5).entity_transforms[
        "box"
    ].translation_mm == pytest.approx((-1, 25, 10))


def test_nested_attachments_follow_in_dependency_order(document):
    raw = document.model_dump()
    raw["entities"]["box"]["interfaces"] = {"top": {"id": "top", "component_id": "box"}}
    raw["interactions"] = raw["interactions"][:4]
    raw["interactions"].insert(
        0,
        Interaction(
            id="box-holds-table",
            actor_id="box",
            target_id="table",
            interaction_type="GRASP",
            actor_interface="top",
        ).model_dump(),
    )
    scene = SceneDocument.model_validate(raw)
    assert evaluate_scene(scene, 5).entity_transforms[
        "table"
    ].translation_mm == pytest.approx((-24, 0, 11))


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda d: d.update(version=2), "version"),
        (lambda d: d["interactions"][1].update(target_id="missing"), "unknown entity"),
        (
            lambda d: d["interactions"][1].update(actor_interface="missing"),
            "unknown actor interface",
        ),
        (
            lambda d: d["interactions"][1].update(actor_interface=None),
            "requires an actor interface",
        ),
        (
            lambda d: d["interactions"][0].update(component_poses={"missing": {}}),
            "unknown actor component",
        ),
        (lambda d: d["interactions"][0].update(duration_s=0), "positive duration"),
        (lambda d: d["interactions"][0].update(duration_s=float("nan")), "finite"),
        (
            lambda d: d["interactions"].insert(
                2, d["interactions"][1] | {"id": "again"}
            ),
            "already grasped",
        ),
        (lambda d: d["interactions"][5].update(actor_id="table"), "current holder"),
        (
            lambda d: d["interactions"][5].update(destination_id="missing"),
            "destination",
        ),
        (
            lambda d: d["interactions"][2].update(id=d["interactions"][0]["id"]),
            "unique",
        ),
        (
            lambda d: d["entities"]["table"]["assembly"]["components"]["table"].update(
                geometry_refs=["box"]
            ),
            "unique",
        ),
    ],
)
def test_rejects_invalid_documents(document, mutate, match):
    raw = document.model_dump()
    mutate(raw)
    with pytest.raises(ValueError, match=match):
        SceneDocument.model_validate(raw)


def test_rejects_attachment_cycles_and_independent_motion_of_held_root(document):
    raw = document.model_dump()
    raw["entities"]["box"]["interfaces"] = {"top": {"id": "top", "component_id": "box"}}
    raw["interactions"].insert(
        2,
        Interaction(
            id="cycle",
            actor_id="box",
            target_id="arm",
            interaction_type="GRASP",
            actor_interface="top",
        ).model_dump(),
    )
    with pytest.raises(ValueError, match="cycle"):
        SceneDocument.model_validate(raw)
    raw["interactions"][2] = Interaction(
        id="move-held",
        actor_id="box",
        target_id="arm",
        interaction_type="MOVE",
        duration_s=1,
        actor_pose={},
    ).model_dump()
    with pytest.raises(ValueError, match="attached"):
        SceneDocument.model_validate(raw)


@pytest.mark.parametrize("time", [-1, float("inf"), float("nan")])
def test_rejects_invalid_sample_time(document, time):
    with pytest.raises(ValueError):
        evaluate_scene(document, time)


def test_shared_browser_parity_samples_are_current(
    document, assert_scene_state_matches
):
    samples = json.loads((EXAMPLES / "robotPickPlaceLegacy.states.json").read_text())
    for sample in samples:
        assert_scene_state_matches(
            evaluate_scene(document, sample["time_s"]),
            SceneState.model_validate(sample),
        )


def test_state_parity_accepts_observed_windows_quaternion_roundoff(
    assert_scene_state_matches,
):
    samples = json.loads((EXAMPLES / "robotPickPlaceLegacy.states.json").read_text())
    reference = SceneState.model_validate(next(s for s in samples if s["time_s"] == 4))
    windows = reference.model_copy(deep=True)
    # Exact values from the Windows CI failure; all other state fields matched.
    windows.component_transforms["arm"]["shoulder"].rotation_quaternion_xyzw = (
        0.0,
        0.0,
        0.38268343236508967,
        0.9238795325112867,
    )
    assert windows != reference
    assert_scene_state_matches(windows, reference)


@pytest.mark.parametrize(
    "field",
    ["translation", "rotation", "attachment", "placement", "interaction", "shape"],
)
def test_state_parity_rejects_meaningful_changes(
    document, assert_scene_state_matches, field
):
    reference = evaluate_scene(document, 4)
    changed = reference.model_copy(deep=True)
    if field == "translation":
        pose = changed.entity_transforms["box"]
        x, y, z = pose.translation_mm
        pose.translation_mm = (x + 1e-6, y, z)
    elif field == "rotation":
        pose = changed.component_transforms["arm"]["shoulder"]
        x, y, z, w = pose.rotation_quaternion_xyzw
        pose.rotation_quaternion_xyzw = (x, y, z + 1e-6, w)
    elif field == "attachment":
        changed.attachments["box"].actor_interface = "different-grip"
    elif field == "placement":
        changed.placements["box"] = "table"
    elif field == "interaction":
        changed.interaction_states["Carry to table"] = "completed"
    else:
        del changed.shape_transforms["box"]
    with pytest.raises(AssertionError):
        assert_scene_state_matches(changed, reference)


def test_world_motion_carries_target_and_can_regrasp_after_release(document):
    from opencad import RigidTransform

    scene = document.model_dump()
    scene["interactions"] = scene["interactions"][:2] + [
        Interaction(
            id="move-root",
            actor_id="arm",
            target_id="box",
            interaction_type="MOVE",
            duration_s=1,
            actor_pose=RigidTransform(
                translation_mm=(10, 20, 30),
                rotation_quaternion_xyzw=(0, 0, 2**-0.5, 2**-0.5),
            ),
        ).model_dump(),
        Interaction(
            id="release", actor_id="arm", target_id="box", interaction_type="RELEASE"
        ).model_dump(),
        Interaction(
            id="regrasp",
            actor_id="arm",
            target_id="box",
            interaction_type="GRASP",
            actor_interface="grip",
        ).model_dump(),
    ]
    state = evaluate_scene(SceneDocument.model_validate(scene), 3)
    assert state.entity_transforms["box"].translation_mm == pytest.approx((10, 44, 32))
    assert state.attachments["box"].actor_id == "arm"
