"""Deterministic kinematic replay; no physics or inverse kinematics required."""

from __future__ import annotations

import math

from opencad.kernel.core.models import RigidTransform
from opencad.kinematics import compose_transforms, _normalize_quaternion, _rotate_vector
from opencad.scene.models import Attachment, SceneDocument, SceneState


def inverse_transform(transform: RigidTransform) -> RigidTransform:
    x, y, z, w = _normalize_quaternion(transform.rotation_quaternion_xyzw)
    inverse = (-x, -y, -z, w)
    return RigidTransform(
        translation_mm=_rotate_vector(
            inverse, tuple(-v for v in transform.translation_mm)
        ),
        rotation_quaternion_xyzw=inverse,
    )


def interpolate_transform(
    start: RigidTransform, end: RigidTransform, t: float
) -> RigidTransform:
    a = _normalize_quaternion(start.rotation_quaternion_xyzw)
    b = _normalize_quaternion(end.rotation_quaternion_xyzw)
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-v for v in b), -dot
    if dot > 0.9995:
        q = _normalize_quaternion(tuple(x + t * (y - x) for x, y in zip(a, b)))
    else:
        angle = math.acos(min(1.0, dot))
        q = tuple(
            (math.sin((1 - t) * angle) * x + math.sin(t * angle) * y) / math.sin(angle)
            for x, y in zip(a, b)
        )
    return RigidTransform(
        translation_mm=tuple(
            x + t * (y - x) for x, y in zip(start.translation_mm, end.translation_mm)
        ),
        rotation_quaternion_xyzw=q,
    )


def scene_duration(document: SceneDocument) -> float:
    return sum(action.duration_s for action in document.interactions)


def evaluate_scene(document: SceneDocument, time_s: float | None = None) -> SceneState:
    """Sample from the initial scene, so seeking backwards/reset never accumulates drift.

    At a boundary, zero-duration events execute in document order. GRASP preserves
    the target's world pose. RELEASE/PLACE freeze it at the event's world pose.
    """
    requested = document.time_s if time_s is None else time_s
    if not math.isfinite(requested) or requested < 0:
        raise ValueError("Scene time must be finite and non-negative.")
    time = min(requested, scene_duration(document))
    entities = {
        key: value.transform.model_copy(deep=True)
        for key, value in document.entities.items()
    }
    components = {
        key: {
            cid: component.transform.model_copy(deep=True)
            for cid, component in entity.assembly.components.items()
        }
        for key, entity in document.entities.items()
    }
    attachments: dict[str, Attachment] = {}
    placements: dict[str, str] = {}
    states = {action.id: "pending" for action in document.interactions}

    def component_world(entity_id: str) -> dict[str, RigidTransform]:
        entity = document.entities[entity_id]
        result: dict[str, RigidTransform] = {}

        def walk(cid: str, parent: RigidTransform) -> None:
            result[cid] = compose_transforms(parent, components[entity_id][cid])
            for child in entity.assembly.components[cid].child_ids:
                walk(child, result[cid])

        for root in entity.assembly.root_ids:
            walk(root, entities[entity_id])
        return result

    def interface_world(actor_id: str, interface_id: str) -> RigidTransform:
        interface = document.entities[actor_id].interfaces[interface_id]
        return compose_transforms(
            component_world(actor_id)[interface.component_id], interface.transform
        )

    def update_attachments() -> None:
        done: set[str] = set()

        def update(target: str) -> None:
            if target in done or target not in attachments:
                return
            attachment = attachments[target]
            update(attachment.actor_id)
            entities[target] = compose_transforms(
                interface_world(attachment.actor_id, attachment.actor_interface),
                attachment.relative_transform,
            )
            done.add(target)

        for target in attachments:
            update(target)

    elapsed = 0.0
    for action in document.interactions:
        if elapsed > time:
            break
        actor, target = action.actor_id, action.target_id
        if action.interaction_type == "MOVE":
            t = min(1.0, (time - elapsed) / action.duration_s)
            if action.actor_pose is not None:
                entities[actor] = interpolate_transform(
                    entities[actor], action.actor_pose, t
                )
                if t > 0:
                    placements.pop(actor, None)
            for cid, pose in action.component_poses.items():
                components[actor][cid] = interpolate_transform(
                    components[actor][cid], pose, t
                )
            update_attachments()
            states[action.id] = "completed" if t == 1 else "active"
            elapsed += action.duration_s
            if t < 1:
                break
        else:
            update_attachments()
            if action.interaction_type == "GRASP":
                attachments[target] = Attachment(
                    actor_id=actor,
                    actor_interface=action.actor_interface,
                    target_id=target,
                    relative_transform=compose_transforms(
                        inverse_transform(
                            interface_world(actor, action.actor_interface)
                        ),
                        entities[target],
                    ),
                )
                placements.pop(target, None)
            else:
                del attachments[target]
                if action.interaction_type == "PLACE":
                    placements[target] = action.destination_id
            states[action.id] = "completed"
    shape_transforms: dict[str, RigidTransform] = {}
    for entity_id, entity in document.entities.items():
        worlds = component_world(entity_id)
        for cid, component in entity.assembly.components.items():
            for ref in component.geometry_refs:
                shape_transforms[ref] = worlds[cid]
    return SceneState(
        time_s=time,
        entity_transforms=entities,
        component_transforms=components,
        shape_transforms=shape_transforms,
        attachments=attachments,
        placements=placements,
        interaction_states=states,
    )
