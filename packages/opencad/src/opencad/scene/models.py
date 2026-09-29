"""Scene identity and temporal interactions, independent of assembly ownership."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from opencad.assembly import AssemblyTree
from opencad.kernel.core.models import RigidTransform


class SceneModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SceneInterface(SceneModel):
    id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    transform: RigidTransform = Field(default_factory=RigidTransform.identity)


class SceneCollider(SceneModel):
    """An oriented box in component-local coordinates; compound parts use several."""

    id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    size_mm: tuple[FiniteFloat, FiniteFloat, FiniteFloat]
    transform: RigidTransform = Field(default_factory=RigidTransform.identity)

    @model_validator(mode="after")
    def validate_size(self) -> "SceneCollider":
        if self.id == "$ground" or any(size <= 0 for size in self.size_mm):
            raise ValueError(
                "Collider IDs must not be $ground and box sizes must be positive."
            )
        return self


class SceneEntity(SceneModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    assembly: AssemblyTree
    transform: RigidTransform = Field(default_factory=RigidTransform.identity)
    interfaces: dict[str, SceneInterface] = Field(default_factory=dict)
    colliders: list[SceneCollider] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interfaces(self) -> SceneEntity:
        for key, interface in self.interfaces.items():
            if (
                key != interface.id
                or interface.component_id not in self.assembly.components
            ):
                raise ValueError(
                    "Interface must have a matching ID and an existing component."
                )
        for collider in self.colliders:
            if collider.component_id not in self.assembly.components:
                raise ValueError("Collider references an unknown component.")
        return self


class Interaction(SceneModel):
    id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    interaction_type: Literal["MOVE", "GRASP", "RELEASE", "PLACE"]
    actor_interface: str | None = None
    # MOVE animates the actor's world pose and/or its components' local poses.
    duration_s: FiniteFloat = Field(default=0, ge=0)
    actor_pose: RigidTransform | None = None
    component_poses: dict[str, RigidTransform] = Field(default_factory=dict)
    # PLACE releases at the current world pose and records the support entity.
    destination_id: str | None = None

    @model_validator(mode="after")
    def validate_action(self) -> Interaction:
        if self.actor_id == self.target_id:
            raise ValueError(
                "An interaction requires distinct actor and target entities."
            )
        if self.interaction_type == "MOVE":
            if self.duration_s <= 0 or (
                self.actor_pose is None and not self.component_poses
            ):
                raise ValueError(
                    "MOVE requires a positive duration and an explicit actor/component pose."
                )
        elif self.duration_s or self.actor_pose is not None or self.component_poses:
            raise ValueError("Only MOVE accepts duration and pose keyframes.")
        if self.interaction_type == "GRASP" and self.actor_interface is None:
            raise ValueError("GRASP requires an actor interface.")
        if (self.interaction_type == "PLACE") != (self.destination_id is not None):
            raise ValueError("Only PLACE requires a destination entity.")
        return self


class SceneDocument(SceneModel):
    """Versioned, replayable scene. Time is the saved playback cursor in seconds."""

    version: Literal[1] = 1
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    entities: dict[str, SceneEntity]
    interactions: list[Interaction] = Field(default_factory=list)
    time_s: FiniteFloat = Field(default=0, ge=0)
    ground_z_mm: FiniteFloat | None = None
    collision_exclusions: list[tuple[str, str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> SceneDocument:
        colliders = [
            c.id for entity in self.entities.values() for c in entity.colliders
        ]
        if len(colliders) != len(set(colliders)):
            raise ValueError("Collider IDs must be unique across the scene.")
        for a, b in self.collision_exclusions:
            if a == b or a not in colliders or b not in colliders:
                raise ValueError(
                    "Collision exclusions require two distinct existing collider IDs."
                )
        geometry: set[str] = set()
        for key, entity in self.entities.items():
            if key != entity.id:
                raise ValueError("Entity map key must match its stable ID.")
            for component in entity.assembly.components.values():
                for ref in component.geometry_refs:
                    if ref in geometry:
                        raise ValueError(
                            "Geometry occurrence IDs must be unique across the scene."
                        )
                    geometry.add(ref)
        ids: set[str] = set()
        # Validate the complete sequence, including conflicts beyond the saved cursor.
        holders: dict[str, str] = {}
        for action in self.interactions:
            if action.id in ids:
                raise ValueError("Interaction IDs must be unique.")
            ids.add(action.id)
            if (
                action.actor_id not in self.entities
                or action.target_id not in self.entities
            ):
                raise ValueError("Interaction references an unknown entity.")
            actor = self.entities[action.actor_id]
            if (
                action.actor_interface is not None
                and action.actor_interface not in actor.interfaces
            ):
                raise ValueError("Interaction references an unknown actor interface.")
            if set(action.component_poses) - actor.assembly.components.keys():
                raise ValueError("MOVE references an unknown actor component.")
            if (
                action.interaction_type == "MOVE"
                and action.actor_pose is not None
                and action.actor_id in holders
            ):
                raise ValueError(
                    "Cannot move an attached entity's world pose independently."
                )
            if action.interaction_type == "GRASP":
                if action.target_id in holders:
                    raise ValueError(
                        "Target is already grasped; release it before transfer."
                    )
                cursor = action.actor_id
                while cursor in holders:
                    cursor = holders[cursor]
                    if cursor == action.target_id:
                        raise ValueError("Attachment graph contains a cycle.")
                holders[action.target_id] = action.actor_id
            if action.interaction_type in ("RELEASE", "PLACE"):
                if holders.get(action.target_id) != action.actor_id:
                    raise ValueError(
                        "Only the current holder can release/place a target."
                    )
                del holders[action.target_id]
            if action.destination_id is not None:
                if (
                    action.destination_id not in self.entities
                    or action.destination_id in (action.actor_id, action.target_id)
                ):
                    raise ValueError(
                        "PLACE requires a distinct existing destination entity."
                    )
        return self


class Attachment(SceneModel):
    actor_id: str
    actor_interface: str
    target_id: str
    relative_transform: RigidTransform


class SceneState(SceneModel):
    time_s: float
    entity_transforms: dict[str, RigidTransform]
    component_transforms: dict[str, dict[str, RigidTransform]]
    shape_transforms: dict[str, RigidTransform]
    attachments: dict[str, Attachment]
    placements: dict[str, str]
    interaction_states: dict[str, Literal["pending", "active", "completed"]]
