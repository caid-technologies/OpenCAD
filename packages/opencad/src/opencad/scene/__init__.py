"""Independent scene roots and temporary physical relationships."""

from opencad.scene.models import (
    Attachment,
    Interaction,
    SceneDocument,
    SceneCollider,
    SceneEntity,
    SceneInterface,
    SceneState,
)
from opencad.scene.playback import evaluate_scene, scene_duration
from opencad.scene.collision import MotionCheck, validate_scene_motion


def serialize_scene(document: SceneDocument) -> str:
    return document.model_dump_json()


def deserialize_scene(payload: str) -> SceneDocument:
    return SceneDocument.model_validate_json(payload)


__all__ = [
    "MotionCheck",
    "validate_scene_motion",
    "Attachment",
    "Interaction",
    "SceneDocument",
    "SceneCollider",
    "SceneEntity",
    "SceneInterface",
    "SceneState",
    "evaluate_scene",
    "scene_duration",
    "serialize_scene",
    "deserialize_scene",
]
