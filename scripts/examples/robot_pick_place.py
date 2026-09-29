"""Regenerate the shared, offline viewport example and Python/TS parity fixture.

Run from the repository root: uv run --no-sync python scripts/examples/robot_pick_place.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from opencad import AssemblyComponent, AssemblyTree, RigidTransform
from opencad.scene import (
    Interaction,
    SceneDocument,
    SceneEntity,
    SceneInterface,
    SceneCollider,
    evaluate_scene,
)


def pose(x=0, y=0, z=0, angle=0):
    half = math.radians(angle) / 2
    return RigidTransform(
        translation_mm=(x, y, z),
        rotation_quaternion_xyzw=(0, 0, math.sin(half), math.cos(half)),
    )


def component(id, children=(), transform=None):
    return AssemblyComponent(
        id=id,
        name=id.replace("-", " ").title(),
        child_ids=list(children),
        geometry_refs=[id],
        transform=transform or pose(),
    )


def build_scene():
    arm = SceneEntity(
        id="arm",
        name="Robot arm",
        assembly=AssemblyTree(
            id="robot-assembly",
            name="Robot arm",
            root_ids=["base"],
            components={
                "base": component("base", ["lift"]),
                "lift": component("lift", ["shoulder"], pose(z=11)),
                "shoulder": component("shoulder", ["elbow"], pose(angle=-60)),
                "elbow": component("elbow", ["gripper"], pose(x=12, z=3, angle=30)),
                "gripper": component(
                    "gripper", ["jaw-left", "jaw-right"], transform=pose(x=12)
                ),
                "jaw-left": component("jaw-left", transform=pose(y=-4.5)),
                "jaw-right": component("jaw-right", transform=pose(y=4.5)),
            },
        ),
        interfaces={
            "grip": SceneInterface(
                id="grip", component_id="gripper", transform=pose(z=-4)
            )
        },
    )

    def entity(id, name, transform):
        return SceneEntity(
            id=id,
            name=name,
            transform=transform,
            assembly=AssemblyTree(
                id=f"{id}-assembly",
                name=name,
                root_ids=[id],
                components={id: component(id)},
            ),
        )

    def move(id, duration, **poses):
        return Interaction(
            id=id,
            actor_id="arm",
            target_id="box",
            interaction_type="MOVE",
            duration_s=duration,
            component_poses=poses,
        )

    return SceneDocument(
        id="robot-pick-place",
        name="Robot pick and place",
        entities={
            "arm": arm,
            "box": entity("box", "Box", pose(x=24, z=2)),
            "table": entity("table", "Destination table", pose(y=24, z=3)),
        },
        ground_z_mm=0,
        interactions=[
            move("Approach above box", 2, shoulder=pose(), elbow=pose(x=12, z=3)),
            move("Descend with open jaws", 1, lift=pose(z=3)),
            move(
                "Close jaws",
                0.5,
                **{"jaw-left": pose(y=-2.5), "jaw-right": pose(y=2.5)},
            ),
            Interaction(
                id="Grasp box",
                actor_id="arm",
                target_id="box",
                actor_interface="grip",
                interaction_type="GRASP",
            ),
            move("Lift clear", 1, lift=pose(z=11)),
            move("Carry to table", 2, shoulder=pose(angle=90)),
            move("Lower onto table", 1, lift=pose(z=9)),
            Interaction(
                id="Place and release",
                actor_id="arm",
                target_id="box",
                interaction_type="PLACE",
                destination_id="table",
            ),
            move(
                "Open jaws", 0.5, **{"jaw-left": pose(y=-4.5), "jaw-right": pose(y=4.5)}
            ),
            move("Retract vertically", 1, lift=pose(z=15)),
            move(
                "Return above obstacles",
                2,
                shoulder=pose(angle=-60),
                elbow=pose(x=12, z=3, angle=30),
            ),
            move("Lower to home", 1, lift=pose(z=11)),
        ],
    )


def cuboids(id, boxes):
    vertices, faces = [], []
    for (x, y, z), (w, d, h) in boxes:
        offset = len(vertices) // 3
        for dx, dy, dz in [
            (-1, -1, -1),
            (1, -1, -1),
            (1, 1, -1),
            (-1, 1, -1),
            (-1, -1, 1),
            (1, -1, 1),
            (1, 1, 1),
            (-1, 1, 1),
        ]:
            vertices.extend([x + dx * w / 2, y + dy * d / 2, z + dz * h / 2])
        faces.extend(
            offset + i
            for i in [
                0,
                2,
                1,
                0,
                3,
                2,
                4,
                5,
                6,
                4,
                6,
                7,
                0,
                1,
                5,
                0,
                5,
                4,
                1,
                2,
                6,
                1,
                6,
                5,
                2,
                3,
                7,
                2,
                7,
                6,
                3,
                0,
                4,
                3,
                4,
                7,
            ]
        )
    return {"shapeId": id, "name": id.title(), "vertices": vertices, "faces": faces}


if __name__ == "__main__":
    scene = build_scene()
    meshes = [
        cuboids("base", [((-5, 0, 0.5), (8, 8, 1)), ((-5, 0, 11), (3, 3, 20))]),
        # Four bars leave a real 4 x 4 mm bore around the 3 x 3 mm rail.
        cuboids(
            "lift",
            [
                ((-5, -2.5, 0), (6, 1, 4)),
                ((-5, 2.5, 0), (6, 1, 4)),
                ((-7.5, 0, 0), (1, 4, 4)),
                ((-2.5, 0, 0), (1, 4, 4)),
                ((-1, 0, -0.5), (2, 3, 1)),
            ],
        ),
        cuboids("shoulder", [((0, 0, 1.5), (2, 2, 3)), ((6, 0, 1.5), (12, 3, 3))]),
        # Stepped link heights keep rotating joints in surface contact.
        cuboids("elbow", [((0, 0, 1.25), (2, 2, 2.5)), ((5, 0, 1.25), (10, 2.5, 2.5))]),
        cuboids("gripper", [((0, 0, 0), (4, 10, 2))]),
        cuboids("jaw-left", [((0, 0, -3.25), (4, 1, 4.5))]),
        cuboids("jaw-right", [((0, 0, -3.25), (4, 1, 4.5))]),
        cuboids("box", [((0, 0, 0), (4, 4, 4))]),
        cuboids(
            "table",
            [
                ((0, 0, 2), (12, 12, 2)),
                ((-4, -4, -1), (2, 2, 4)),
                ((4, -4, -1), (2, 2, 4)),
                ((-4, 4, -1), (2, 2, 4)),
                ((4, 4, -1), (2, 2, 4)),
            ],
        ),
    ]
    by_shape = {m["shapeId"]: m for m in meshes}
    for entity in scene.entities.values():
        for cid, item in entity.assembly.components.items():
            for ref in item.geometry_refs:
                vertices = by_shape[ref]["vertices"]
                for index in range(0, len(vertices), 24):
                    chunk = vertices[index : index + 24]
                    low = [min(chunk[axis::3]) for axis in range(3)]
                    high = [max(chunk[axis::3]) for axis in range(3)]
                    entity.colliders.append(
                        SceneCollider(
                            id=f"{ref}-{index // 24}",
                            component_id=cid,
                            size_mm=tuple(b - a for a, b in zip(low, high)),
                            transform=RigidTransform(
                                translation_mm=tuple(
                                    (a + b) / 2 for a, b in zip(low, high)
                                )
                            ),
                        )
                    )
    scene = SceneDocument.model_validate(scene.model_dump())
    root = Path(__file__).resolve().parents[2]
    folder = root / "packages/opencad-viewport/src/examples"
    (folder / "robotPickPlace.json").write_text(
        json.dumps(
            {"document": scene.model_dump(mode="json"), "meshes": meshes}, indent=2
        )
        + "\n"
    )
    samples = [
        evaluate_scene(scene, time).model_dump(mode="json")
        for time in [0, 1, 2, 3, 3.5, 4, 4.5, 5.5, 6.5, 7.5, 8, 9, 12]
    ]
    (folder / "robotPickPlace.states.json").write_text(
        "[\n" + ",\n".join(json.dumps(sample) for sample in samples) + "\n]" + "\n"
    )
    print("Wrote scene, meshes, and 13 cross-language playback samples.")
