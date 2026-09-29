# Scene interactions

OpenCAD scenes describe independent machines and objects and their temporary
relationships. An entity owns an `AssemblyTree`; grasping never reparents an
assembly component or changes feature history. Stable scene entity, component,
interface and interaction IDs are independent of regeneratable geometry refs.
Geometry refs identify **occurrences** and must be unique throughout a scene.

## Try the robot pick-and-place example

From the repository root:

```bash
pnpm install
pnpm --filter opencad-viewport build
pnpm --filter opencad-viewport-app dev
```

Open http://localhost:5173 and select **Robot pick-and-place demo**, then **Play**.
The arm approaches above the box, descends with open jaws, closes and grasps,
lifts clear, carries to the table, releases, opens its jaws, and retracts vertically.
It returns above the obstacles before lowering to its home height. The box highlights blue while
held. Pause, scrub backwards, or Reset to inspect exact attachment boundaries.
**Save scene** downloads the document including its current playback cursor.
This example works offline, with no backend or model credentials. Its meshes
and compound box colliders share the same geometry. The 12-second sequence has
complete collider coverage and passes validation without collision exclusions.
The sliding carriage has an actual bore around the lift rail, and joint link
heights are stepped to permit rotation without solid overlap.

## Document and coordinate contract

`SceneDocument` is a version-1 JSON document with an entity map, an ordered
interaction list, and `time_s` (the saved playback cursor). `SceneEntity` holds its
own assembly, initial world transform, and named interfaces. Each `SceneInterface`
is a transform relative to a stable assembly component ID.

All transforms use millimeters, Z-up coordinates and XYZW quaternions. Entity
transforms are world poses; component transforms are **parent-local** poses;
mesh vertices are local to the owning component. Component worlds compose from
the entity through the assembly hierarchy. Consumers with meshes already baked
into world coordinates must convert them to the appropriate component frame.

| Interaction | Behavior |
|---|---|
| `MOVE` | Interpolate the actor's world `actor_pose` and/or parent-local `component_poses` over a positive `duration_s`. `target_id` identifies the interaction's object/context; it is not an IK goal. |
| `GRASP` | Attach `target_id` to the actor's named `actor_interface`, preserving the current relative position and orientation. |
| `RELEASE` | Remove the holder relationship; retain the target's current world pose. |
| `PLACE` | Release at the current world pose and record `destination_id` as the support entity. This already includes release; do not append a second `RELEASE`. |

The sequence is serial. Discrete events consume no time and execute in list
order at the preceding move's end. Translation interpolates linearly and
rotation uses shortest-path quaternion interpolation. Supply explicit component
poses to articulate joints; existing `evaluate_joint_pose` can help author these
poses, but it does not automatically solve for a destination. Component-local
origins should be placed at joint pivots.

GRASP does not snap or test contact. MOVE does not solve IK, enforce joint limits,
plan a collision-free path, or simulate forces. PLACE records support semantics;
it does not check the table surface or make the box follow future table motion.
The example authors the final box pose so its bottom meets the table top.

Attachments form a separate directed graph. A target has one holder at a time;
cycles, missing references and competing holders are rejected. An attached
entity may articulate its own components, but cannot independently override its
world pose. Release before transferring it to another holder. Nested acyclic
attachments are evaluated in dependency order.

## Collision validation and viewport behavior

Each entity may provide `colliders`: component-local `SceneCollider` boxes with
stable scene-wide IDs, positive `size_mm`, and a local `transform`. Use multiple
boxes for concave/compound parts (including a gripper's separate moving jaws).
These are authored collision proxies, not an automatic mesh decomposition.
The demo's proxies match its constituent cuboids exactly; for other geometry,
clearance guarantees apply only to the supplied collider representation.

`validate_scene_motion(scene)` in Python and `validateSceneMotion(scene)` in
TypeScript validate the entire authored timeline, including robot self-collision,
carried objects, nested attachments, and optional `ground_z_mm`. They compare
oriented boxes with separating axes and bound projected point travel over each
interval. Intervals that cannot be certified are subdivided, so the check covers
rotation and fast crossings between display frames rather than relying on a
fixed frame rate. Shared ancestor motion is cancelled to handle grasped objects
and surface contact correctly.

The default allowed penetration tolerance is 0.001 mm. Surface contact is allowed;
GRASP and PLACE never exempt an object from penetration checks. Colliders in the
same rigid component are treated as a compound solid. `collision_exclusions`
can explicitly omit selected collider-ID pairs for authored joint geometry;
the example needs none. Exclusions and the tolerance are part of the scope of
any reported clearance result. Keep exclusions narrowly targeted.

The result is a serializable `MotionCheck`:

| Status | Meaning |
|---|---|
| `clear` | The requested interval is certified against the authored colliders and tolerance. |
| `collision` | Penetration was detected; the report names the collider and shape IDs. |
| `uncertain` | An interval could not be certified within the subdivision/precision budget. Motion is blocked conservatively. |
| `unchecked` | Some visible components have no colliders, or the scene has none; this is not a clearance guarantee. Known collisions still block. |

`safe_time_s` is the end of the certified prefix; `time_s` locates the offending
interval/sample. An initially invalid scene is blocked at zero. Collision checking
is separate from `evaluate_scene`/`evaluateScene`, which remain unrestricted pose
samplers for inspection and authoring.

`ScenePlayer` preflights the timeline and applies the same limit to playback,
scrubbing, and restored saved cursors. It pauses at the last certified time,
names the pair, and highlights it red for detected penetration or amber when
validation is inconclusive. Scenes with missing proxies remain playable and show
that their collision coverage is incomplete. To change a blocked sequence, edit
its geometry or waypoints and pass a new document to the player.

```python
from opencad import validate_scene_motion

check = validate_scene_motion(scene)
if check.status == "clear":
    state = evaluate_scene(scene, 5.5)
else:
    print(check.model_dump())
```

This validates authored trajectories. It does not automatically plan a new route,
solve IK, enforce actuator limits, simulate forces, or verify hardware safety.

## Python

```python
from pathlib import Path
from opencad import deserialize_scene, evaluate_scene, serialize_scene

scene = deserialize_scene(Path("robot-pick-place.scene.json").read_text())
state = evaluate_scene(scene)       # uses the saved cursor
state = evaluate_scene(scene, 4.0)  # sample any time deterministically
print(state.attachments)
print(state.shape_transforms)      # renderer-ready world poses by geometry ref

scene.time_s = 4.0
Path("saved.scene.json").write_text(serialize_scene(scene))
```

Author documents using `SceneDocument`, `SceneEntity`, `SceneInterface` and
`Interaction`, exported from `opencad` and `opencad.scene`. For a complete authored
example, see [`scripts/examples/robot_pick_place.py`](../scripts/examples/robot_pick_place.py).

`SceneState` is also JSON serializable and includes entity/component/shape poses,
active attachments with relative transforms, recorded placements and each
interaction's pending/active/completed status. Restore using the document plus
cursor: replay reconstructs this state without drift or dependency on prior
render frames. Standalone state is an inspection result, not a replacement for
the authored timeline. Older feature-tree and assembly snapshots stay unchanged.

## React

```tsx
import { ScenePlayer, robotPickPlaceExample } from "opencad-viewport";
import "opencad-viewport/styles.css";

<ScenePlayer
  document={robotPickPlaceExample.document}
  meshes={robotPickPlaceExample.meshes}
/>
```

For custom playback, `createScenePlayer(document)` validates and takes a private
snapshot, returning a reusable `(time_s) => SceneState` sampler. Pass its
`shape_transforms` to `Viewport3D.shapeTransforms`. `evaluateScene(document, time)`
is the one-shot equivalent. Validate newly authored browser documents with
`validateScene` before saving or rendering them.

The generated example and cross-language expected samples are shared by Python
and TypeScript tests. Regenerate intentionally with:

```bash
uv run --no-sync python scripts/examples/robot_pick_place.py
```

Future interaction types, richer interfaces, constraints, mesh-level contact checking and
physics can build on the scene/interaction boundary without merging assemblies.
Version the document contract when adding incompatible semantics.
