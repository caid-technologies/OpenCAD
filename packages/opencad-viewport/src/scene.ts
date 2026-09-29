import { Quaternion, Vector3 } from "three";
import type { AssemblyTreeView, RigidTransform } from "./types";
import {
  IDENTITY_RIGID_TRANSFORM as identity,
  normalizeRigidTransform,
} from "./shapeTransforms";

export interface SceneInterface {
  id: string;
  component_id: string;
  transform: RigidTransform;
}
export interface SceneCollider {
  id: string;
  component_id: string;
  size_mm: [number, number, number];
  transform: RigidTransform;
}
export interface SceneEntity {
  id: string;
  name: string;
  assembly: AssemblyTreeView;
  transform: RigidTransform;
  interfaces: Record<string, SceneInterface>;
  colliders?: SceneCollider[];
}
export interface Interaction {
  id: string;
  actor_id: string;
  target_id: string;
  interaction_type: "MOVE" | "GRASP" | "RELEASE" | "PLACE";
  actor_interface: string | null;
  duration_s: number;
  actor_pose: RigidTransform | null;
  component_poses: Record<string, RigidTransform>;
  destination_id: string | null;
}
export interface SceneDocument {
  version: 1;
  id: string;
  name: string;
  entities: Record<string, SceneEntity>;
  interactions: Interaction[];
  time_s: number;
  ground_z_mm?: number | null;
  collision_exclusions?: [string, string][];
}
export interface Attachment {
  actor_id: string;
  actor_interface: string;
  target_id: string;
  relative_transform: RigidTransform;
}
export interface SceneState {
  time_s: number;
  entity_transforms: Record<string, RigidTransform>;
  component_transforms: Record<string, Record<string, RigidTransform>>;
  shape_transforms: Record<string, RigidTransform>;
  attachments: Record<string, Attachment>;
  placements: Record<string, string>;
  interaction_states: Record<string, "pending" | "active" | "completed">;
}

function quaternion(t: RigidTransform): Quaternion {
  return new Quaternion(...normalizeRigidTransform(t).rotation_quaternion_xyzw);
}
function transform(position: Vector3, rotation: Quaternion): RigidTransform {
  return {
    translation_mm: position.toArray(),
    rotation_quaternion_xyzw: rotation.toArray(),
  };
}
export function composeSceneTransforms(
  a: RigidTransform,
  b: RigidTransform,
): RigidTransform {
  return transform(
    new Vector3(...b.translation_mm)
      .applyQuaternion(quaternion(a))
      .add(new Vector3(...a.translation_mm)),
    quaternion(a).multiply(quaternion(b)),
  );
}
function inverse(t: RigidTransform): RigidTransform {
  const q = quaternion(t).invert();
  return transform(
    new Vector3(...t.translation_mm).negate().applyQuaternion(q),
    q,
  );
}
export function interpolateSceneTransform(
  a: RigidTransform,
  b: RigidTransform,
  t: number,
): RigidTransform {
  const qa = quaternion(a),
    qb = quaternion(b);
  if (qa.dot(qb) < 0) qb.set(-qb.x, -qb.y, -qb.z, -qb.w);
  const q =
    qa.dot(qb) > 0.9995
      ? new Quaternion(
          qa.x + t * (qb.x - qa.x),
          qa.y + t * (qb.y - qa.y),
          qa.z + t * (qb.z - qa.z),
          qa.w + t * (qb.w - qa.w),
        ).normalize()
      : qa.slerp(qb, t);
  return transform(
    new Vector3(...a.translation_mm).lerp(new Vector3(...b.translation_mm), t),
    q,
  );
}

/** Validate authored documents before playback, including the full action graph. */
export function validateScene(document: SceneDocument): void {
  const ensure = (condition: unknown, message: string) => {
    if (!condition) throw new Error(message);
  };
  ensure(document.version === 1, "Unsupported scene version.");
  ensure(
    Number.isFinite(document.time_s) && document.time_s >= 0,
    "Invalid scene time.",
  );
  const has = (map: object, key: string) =>
    Object.prototype.hasOwnProperty.call(map, key);
  const geometry = new Set<string>();
  const colliders = new Set<string>();
  ensure(
    document.ground_z_mm == null || Number.isFinite(document.ground_z_mm),
    "Invalid ground plane.",
  );
  const checkPose = (pose: RigidTransform) =>
    ensure(
      pose.translation_mm.length === 3 &&
        pose.rotation_quaternion_xyzw.length === 4 &&
        [...pose.translation_mm, ...pose.rotation_quaternion_xyzw].every(
          Number.isFinite,
        ),
      "Invalid rigid transform.",
    );
  for (const [id, entity] of Object.entries(document.entities)) {
    ensure(id.length > 0 && id === entity.id, "Entity ID mismatch.");
    checkPose(entity.transform);
    const { components, root_ids } = entity.assembly;
    const parents = new Set<string>();
    for (const [cid, component] of Object.entries(components)) {
      ensure(cid === component.id, "Component ID mismatch.");
      checkPose(component.transform ?? identity);
      for (const child of component.child_ids) {
        ensure(
          has(components, child) && !parents.has(child),
          "Invalid component parentage.",
        );
        parents.add(child);
      }
      for (const ref of component.geometry_refs) {
        ensure(!geometry.has(ref), "Geometry occurrence IDs must be unique.");
        geometry.add(ref);
      }
    }
    ensure(
      new Set(root_ids).size === root_ids.length &&
        root_ids.length === Object.keys(components).length - parents.size,
      "Invalid assembly roots.",
    );
    const visited = new Set<string>();
    const walk = (cid: string) => {
      ensure(
        has(components, cid) && !visited.has(cid),
        "Invalid or cyclic assembly.",
      );
      visited.add(cid);
      components[cid].child_ids.forEach(walk);
    };
    for (const root of root_ids) {
      ensure(!parents.has(root), "Invalid assembly root.");
      walk(root);
    }
    ensure(
      visited.size === Object.keys(components).length,
      "Disconnected or cyclic assembly.",
    );
    for (const collider of entity.colliders ?? []) {
      ensure(
        collider.id && collider.id !== "$ground" && !colliders.has(collider.id),
        "Collider IDs must be unique.",
      );
      colliders.add(collider.id);
      ensure(
        has(components, collider.component_id),
        "Collider references an unknown component.",
      );
      ensure(
        collider.size_mm.length === 3 &&
          collider.size_mm.every(
            (value) => Number.isFinite(value) && value > 0,
          ),
        "Collider sizes must be positive and finite.",
      );
      checkPose(collider.transform);
    }
    for (const [iid, item] of Object.entries(entity.interfaces)) {
      ensure(
        iid === item.id && has(components, item.component_id),
        "Invalid scene interface.",
      );
      checkPose(item.transform);
    }
  }
  for (const pair of document.collision_exclusions ?? []) {
    ensure(
      pair.length === 2 &&
        pair[0] !== pair[1] &&
        pair.every((id) => colliders.has(id)),
      "Invalid collision exclusion.",
    );
  }
  const ids = new Set<string>();
  const holders = new Map<string, string>();
  for (const action of document.interactions) {
    const actor = document.entities[action.actor_id];
    ensure(action.id && !ids.has(action.id), "Interaction IDs must be unique.");
    ids.add(action.id);
    ensure(
      has(document.entities, action.actor_id) &&
        has(document.entities, action.target_id) &&
        action.actor_id !== action.target_id,
      "Invalid interaction entity.",
    );
    ensure(
      ["MOVE", "GRASP", "RELEASE", "PLACE"].includes(action.interaction_type),
      "Unknown interaction type.",
    );
    ensure(
      action.actor_interface == null ||
        has(actor.interfaces, action.actor_interface),
      "Unknown actor interface.",
    );
    ensure(
      Number.isFinite(action.duration_s) && action.duration_s >= 0,
      "Invalid duration.",
    );
    for (const [cid, pose] of Object.entries(action.component_poses)) {
      ensure(has(actor.assembly.components, cid), "Unknown actor component.");
      checkPose(pose);
    }
    if (action.actor_pose) checkPose(action.actor_pose);
    if (action.interaction_type === "MOVE") {
      ensure(
        action.duration_s > 0 &&
          (action.actor_pose || Object.keys(action.component_poses).length),
        "MOVE requires duration and poses.",
      );
      ensure(
        !action.actor_pose || !holders.has(action.actor_id),
        "Cannot move attached entity independently.",
      );
    } else {
      ensure(
        action.duration_s === 0 &&
          !action.actor_pose &&
          !Object.keys(action.component_poses).length,
        "Only MOVE accepts keyframes.",
      );
    }
    if (action.interaction_type === "GRASP") {
      ensure(
        action.actor_interface && has(actor.interfaces, action.actor_interface),
        "GRASP requires an interface.",
      );
      ensure(!holders.has(action.target_id), "Target is already grasped.");
      let cursor = action.actor_id;
      while (holders.has(cursor)) {
        cursor = holders.get(cursor)!;
        ensure(cursor !== action.target_id, "Attachment cycle.");
      }
      holders.set(action.target_id, action.actor_id);
    }
    if (
      action.interaction_type === "RELEASE" ||
      action.interaction_type === "PLACE"
    ) {
      ensure(
        holders.get(action.target_id) === action.actor_id,
        "Only the holder can release/place.",
      );
      holders.delete(action.target_id);
    }
    if (action.interaction_type === "PLACE") {
      ensure(
        action.destination_id &&
          has(document.entities, action.destination_id) &&
          ![action.actor_id, action.target_id].includes(action.destination_id),
        "Invalid placement destination.",
      );
    } else
      ensure(
        action.destination_id == null,
        "Only PLACE accepts a destination.",
      );
  }
}

export function sceneDuration(document: SceneDocument): number {
  return document.interactions.reduce(
    (sum, action) => sum + action.duration_s,
    0,
  );
}

/** Compile once; each sample replays from rest, including exact event boundaries. */
export function createScenePlayer(
  document: SceneDocument,
): (time_s?: number) => SceneState {
  // Own a snapshot: callers cannot invalidate the validated graph during playback.
  const scene = JSON.parse(JSON.stringify(document)) as SceneDocument;
  validateScene(scene);
  return (requested = scene.time_s) => {
    if (!Number.isFinite(requested) || requested < 0)
      throw new Error("Invalid scene time.");
    const time = Math.min(requested, sceneDuration(scene));
    const entities = Object.fromEntries(
      Object.entries(scene.entities).map(([id, entity]) => [
        id,
        entity.transform,
      ]),
    );
    const components = Object.fromEntries(
      Object.entries(scene.entities).map(([id, entity]) => [
        id,
        Object.fromEntries(
          Object.entries(entity.assembly.components).map(([cid, component]) => [
            cid,
            component.transform ?? identity,
          ]),
        ),
      ]),
    );
    const attachments: Record<string, Attachment> = Object.create(null);
    const placements: Record<string, string> = Object.create(null);
    const states: SceneState["interaction_states"] = Object.fromEntries(
      scene.interactions.map((action) => [action.id, "pending"]),
    );
    const componentWorld = (eid: string) => {
      const entity = scene.entities[eid];
      const result: Record<string, RigidTransform> = Object.create(null);
      const walk = (cid: string, parent: RigidTransform) => {
        result[cid] = composeSceneTransforms(parent, components[eid][cid]);
        entity.assembly.components[cid].child_ids.forEach((child) =>
          walk(child, result[cid]),
        );
      };
      entity.assembly.root_ids.forEach((root) => walk(root, entities[eid]));
      return result;
    };
    const interfaceWorld = (eid: string, iid: string) => {
      const item = scene.entities[eid].interfaces[iid];
      return composeSceneTransforms(
        componentWorld(eid)[item.component_id],
        item.transform,
      );
    };
    const updateAttachments = () => {
      const done = new Set<string>();
      const update = (target: string) => {
        if (done.has(target) || !attachments[target]) return;
        const item = attachments[target];
        update(item.actor_id);
        entities[target] = composeSceneTransforms(
          interfaceWorld(item.actor_id, item.actor_interface),
          item.relative_transform,
        );
        done.add(target);
      };
      Object.keys(attachments).forEach(update);
    };
    let elapsed = 0;
    for (const action of scene.interactions) {
      if (elapsed > time) break;
      const actor = action.actor_id,
        target = action.target_id;
      if (action.interaction_type === "MOVE") {
        const t = Math.min(1, (time - elapsed) / action.duration_s);
        if (action.actor_pose) {
          entities[actor] = interpolateSceneTransform(
            entities[actor],
            action.actor_pose,
            t,
          );
          if (t > 0) delete placements[actor];
        }
        for (const [cid, pose] of Object.entries(action.component_poses))
          components[actor][cid] = interpolateSceneTransform(
            components[actor][cid],
            pose,
            t,
          );
        updateAttachments();
        states[action.id] = t === 1 ? "completed" : "active";
        elapsed += action.duration_s;
        if (t < 1) break;
      } else {
        updateAttachments();
        if (action.interaction_type === "GRASP") {
          attachments[target] = {
            actor_id: actor,
            actor_interface: action.actor_interface!,
            target_id: target,
            relative_transform: composeSceneTransforms(
              inverse(interfaceWorld(actor, action.actor_interface!)),
              entities[target],
            ),
          };
          delete placements[target];
        } else {
          delete attachments[target];
          if (action.interaction_type === "PLACE")
            placements[target] = action.destination_id!;
        }
        states[action.id] = "completed";
      }
    }
    const shapes: Record<string, RigidTransform> = Object.create(null);
    for (const [eid, entity] of Object.entries(scene.entities)) {
      const worlds = componentWorld(eid);
      for (const [cid, component] of Object.entries(entity.assembly.components))
        component.geometry_refs.forEach((ref) => {
          shapes[ref] = worlds[cid];
        });
    }
    // Returned state is caller-owned and safe to serialize or modify.
    return JSON.parse(
      JSON.stringify({
        time_s: time,
        entity_transforms: entities,
        component_transforms: components,
        shape_transforms: shapes,
        attachments,
        placements,
        interaction_states: states,
      }),
    ) as SceneState;
  };
}

export function evaluateScene(
  document: SceneDocument,
  time_s = document.time_s,
): SceneState {
  return createScenePlayer(document)(time_s);
}
