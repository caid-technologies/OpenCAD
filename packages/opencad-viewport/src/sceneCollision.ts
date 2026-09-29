import { Quaternion, Vector3 } from "three";
import {
  composeSceneTransforms,
  createScenePlayer,
  interpolateSceneTransform,
  sceneDuration,
} from "./scene";
import type { Interaction, SceneDocument, SceneState } from "./scene";
import type { RigidTransform } from "./types";
import {
  IDENTITY_RIGID_TRANSFORM as identity,
  normalizeRigidTransform,
} from "./shapeTransforms";

export interface MotionCheck {
  status: "clear" | "collision" | "uncertain" | "unchecked";
  safe_time_s: number;
  time_s: number;
  collider_ids: string[];
  shape_ids: string[];
  unchecked_components: string[];
}
export interface CollisionOptions {
  tolerance_mm?: number;
  time_tolerance_s?: number;
  max_depth?: number;
}
interface Link {
  key: string;
  start: RigidTransform;
  end: RigidTransform;
}
interface Box {
  id: string;
  entity: string;
  component: string;
  half: Vector3;
  links: Link[];
  shapes: string[];
}
const vector = (v: [number, number, number]) => new Vector3(...v);
const rotation = (pose: RigidTransform) =>
  new Quaternion(...normalizeRigidTransform(pose).rotation_quaternion_xyzw);
const key = (...ids: string[]) => JSON.stringify(ids);
function angular(link: Link): [number, Vector3] {
  const a = rotation(link.start),
    b = rotation(link.end);
  if (a.dot(b) < 0) b.set(-b.x, -b.y, -b.z, -b.w);
  const dot = a.dot(b);
  const delta = b.clone().multiply(a.clone().invert());
  const axis = new Vector3(delta.x, delta.y, delta.z);
  const sine = axis.length();
  return [
    2 * Math.atan2(sine, Math.max(0, dot)),
    sine > 0 ? axis.divideScalar(sine) : new Vector3(),
  ];
}
function world(links: Link[], progress: number): [Vector3, Quaternion] {
  let pose = identity;
  for (const link of links)
    pose = composeSceneTransforms(
      pose,
      interpolateSceneTransform(link.start, link.end, progress),
    );
  return [vector(pose.translation_mm), rotation(pose)];
}
function travel(links: Link[], half: Vector3, axis: Vector3): number {
  const radii = Array<number>(links.length + 1).fill(0);
  const speeds = Array<number>(links.length + 1).fill(0);
  const angles = links.map(angular);
  radii[links.length] = half.length();
  for (let i = links.length - 1; i >= 0; i--) {
    const a = vector(links[i].start.translation_mm),
      b = vector(links[i].end.translation_mm);
    radii[i] = radii[i + 1] + Math.max(a.length(), b.length());
    // Also bounds normalized-lerp angular speed for tiny quaternions.
    const angle = angles[i][0],
      bound = angle < 0.064 ? 4 * Math.tan(angle / 4) : angle;
    speeds[i] = speeds[i + 1] + a.distanceTo(b) + bound * radii[i + 1];
  }
  function projected(i: number, n: Vector3): number {
    if (i === links.length) return 0;
    const link = links[i];
    const linear = Math.abs(
      n.dot(
        vector(link.end.translation_mm).sub(vector(link.start.translation_mm)),
      ),
    );
    const [angle, rotationAxis] = angles[i];
    if (angle === 0 || rotationAxis.clone().cross(n).length() === 0) {
      return (
        linear +
        projected(
          i + 1,
          n.clone().applyQuaternion(rotation(link.start).invert()),
        )
      );
    }
    const bound = angle < 0.064 ? 4 * Math.tan(angle / 4) : angle;
    return linear + bound * radii[i + 1] + speeds[i + 1];
  }
  return projected(0, axis);
}
function paths(
  document: SceneDocument,
  state: SceneState,
  action?: Interaction,
): Box[] {
  const fixed = (id: string, pose: RigidTransform): Link => ({
    key: id,
    start: pose,
    end: pose,
  });
  function components(eid: string, cid: string): Link[] {
    const entity = document.entities[eid];
    const parents = new Map(
      Object.values(entity.assembly.components).flatMap((c) =>
        c.child_ids.map((child) => [child, c.id] as const),
      ),
    );
    const lineage = [cid];
    while (parents.has(lineage[lineage.length - 1]))
      lineage.push(parents.get(lineage[lineage.length - 1])!);
    return lineage
      .reverse()
      .map((id) => ({
        key: key("component", eid, id),
        start: state.component_transforms[eid][id],
        end:
          action?.actor_id === eid
            ? (action.component_poses[id] ??
              state.component_transforms[eid][id])
            : state.component_transforms[eid][id],
      }));
  }
  function entityPath(eid: string): Link[] {
    const attachment = Object.prototype.hasOwnProperty.call(
      state.attachments,
      eid,
    )
      ? state.attachments[eid]
      : undefined;
    if (attachment) {
      const actor = attachment.actor_id,
        item = document.entities[actor].interfaces[attachment.actor_interface];
      return [
        ...entityPath(actor),
        ...components(actor, item.component_id),
        fixed(key("interface", actor, item.id), item.transform),
        fixed(key("attachment", eid), attachment.relative_transform),
      ];
    }
    const pose = state.entity_transforms[eid];
    return [
      {
        key: key("entity", eid),
        start: pose,
        end: action?.actor_id === eid ? (action.actor_pose ?? pose) : pose,
      },
    ];
  }
  return Object.entries(document.entities).flatMap(([eid, entity]) =>
    (entity.colliders ?? []).map((collider) => ({
      id: collider.id,
      entity: eid,
      component: collider.component_id,
      half: vector(collider.size_mm).multiplyScalar(0.5),
      links: [
        ...entityPath(eid),
        ...components(eid, collider.component_id),
        fixed(key("collider", collider.id), collider.transform),
      ],
      shapes: entity.assembly.components[collider.component_id].geometry_refs,
    })),
  );
}
function axes(q: Quaternion): Vector3[] {
  return [new Vector3(1, 0, 0), new Vector3(0, 1, 0), new Vector3(0, 0, 1)].map(
    (n) => n.applyQuaternion(q),
  );
}
function radius(q: Quaternion, half: Vector3, axis: Vector3): number {
  const n = axis.clone().applyQuaternion(q.clone().invert());
  return (
    Math.abs(n.x) * half.x + Math.abs(n.y) * half.y + Math.abs(n.z) * half.z
  );
}
type PairResult = {
  safe: number;
  hit: number;
  status: "collision" | "uncertain";
};
function pairCheck(
  a: Box,
  b: Box | null,
  low: number,
  high: number,
  tolerance: number,
  ground: number | null | undefined,
  progressTolerance: number,
  maxDepth: number,
): PairResult | null {
  let left = a.links,
    right = b?.links ?? [];
  if (b) {
    let common = 0;
    while (
      common < Math.min(left.length, right.length) &&
      left[common].key === right[common].key
    )
      common++;
    left = left.slice(common);
    right = right.slice(common);
  }
  function measure(progress: number): Array<[number, Vector3]> {
    const [ca, ra] = world(left, progress);
    if (!b) {
      const normal = new Vector3(0, 0, 1);
      return [[ca.z - radius(ra, a.half, normal) - ground!, normal]];
    }
    const [cb, rb] = world(right, progress),
      aa = axes(ra),
      ab = axes(rb);
    return [
      ...aa,
      ...ab,
      ...aa.flatMap((x) => ab.map((y) => x.clone().cross(y))),
    ]
      .filter((n) => n.length() >= 1e-10)
      .map((n) => {
        n.normalize();
        return [
          Math.abs(cb.clone().sub(ca).dot(n)) -
            radius(ra, a.half, n) -
            radius(rb, b.half, n),
          n,
        ];
      });
  }
  function visit(lo: number, hi: number, depth: number): PairResult | null {
    const mid = (lo + hi) / 2,
      gaps = measure(mid);
    for (const [gap, axis] of gaps) {
      const movement =
        ((travel(left, a.half, axis) + (b ? travel(right, b.half, axis) : 0)) *
          (hi - lo)) /
        2;
      if (gap + tolerance >= movement + 1e-12) return null;
    }
    const penetrating = Math.max(...gaps.map(([gap]) => gap)) < -tolerance;
    if (hi - lo <= progressTolerance || depth >= maxDepth) {
      const atStart = Math.max(...measure(lo).map(([gap]) => gap)) < -tolerance;
      const atEnd = Math.max(...measure(hi).map(([gap]) => gap)) < -tolerance;
      return {
        safe: lo,
        hit: atStart ? lo : penetrating ? mid : hi,
        status: penetrating || atStart || atEnd ? "collision" : "uncertain",
      };
    }
    return visit(lo, mid, depth + 1) ?? visit(mid, hi, depth + 1);
  }
  return visit(low, high, 0);
}

/** Certifies whole intervals using separating axes and conservative travel bounds.
 * Exhausted precision fails closed; missing collider coverage is never "clear".
 * Surface contact is permitted, but GRASP/PLACE never excuse penetration.
 */
export function validateSceneMotion(
  document: SceneDocument,
  start_s = 0,
  end_s = sceneDuration(document),
  options: CollisionOptions = {},
): MotionCheck {
  const tolerance = options.tolerance_mm ?? 0.001,
    timeTolerance = options.time_tolerance_s ?? 0.0001,
    maxDepth = options.max_depth ?? 20;
  if (
    ![start_s, end_s, tolerance, timeTolerance].every(Number.isFinite) ||
    start_s < 0 ||
    end_s < start_s ||
    tolerance < 0 ||
    timeTolerance <= 0 ||
    !Number.isInteger(maxDepth) ||
    maxDepth < 1 ||
    maxDepth > 30
  )
    throw new Error("Invalid motion validation interval or tolerance.");
  const sample = createScenePlayer(document);
  const end = Math.min(end_s, sceneDuration(document)),
    start = Math.min(start_s, end);
  const missing = Object.entries(document.entities).flatMap(([eid, e]) =>
    Object.entries(e.assembly.components)
      .filter(
        ([cid, c]) =>
          c.geometry_refs.length &&
          !(e.colliders ?? []).some((x) => x.component_id === cid),
      )
      .map(([cid]) => `${eid}/${cid}`),
  );
  const ignored = new Set(
    (document.collision_exclusions ?? []).map((pair) =>
      JSON.stringify([...pair].sort()),
    ),
  );
  const segments: Array<{
    origin: number;
    duration: number;
    action?: Interaction;
    lo: number;
    hi: number;
  }> = [];
  let elapsed = 0;
  for (const action of document.interactions) {
    if (action.interaction_type === "MOVE") {
      if (elapsed <= end && elapsed + action.duration_s >= start)
        segments.push({
          origin: elapsed,
          duration: action.duration_s,
          action,
          lo: Math.max(start, elapsed),
          hi: Math.min(end, elapsed + action.duration_s),
        });
      elapsed += action.duration_s;
    }
  }
  if (!segments.length)
    segments.push({ origin: start, duration: 1, lo: start, hi: end });
  for (const { origin, duration, action, lo, hi } of segments) {
    const boxes = paths(document, sample(origin), action);
    const pairs: Array<[Box, Box | null]> = [];
    for (let i = 0; i < boxes.length; i++)
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i],
          b = boxes[j];
        if (
          (a.entity !== b.entity || a.component !== b.component) &&
          !ignored.has(JSON.stringify([a.id, b.id].sort()))
        )
          pairs.push([a, b]);
      }
    if (document.ground_z_mm != null)
      pairs.push(...boxes.map((box) => [box, null] as [Box, null]));
    let first: { result: PairResult; a: Box; b: Box | null } | undefined;
    for (const [a, b] of pairs) {
      const result = pairCheck(
        a,
        b,
        (lo - origin) / duration,
        (hi - origin) / duration,
        tolerance,
        document.ground_z_mm,
        timeTolerance / duration,
        maxDepth,
      );
      if (result && (!first || result.safe < first.result.safe))
        first = { result, a, b };
    }
    if (first)
      return {
        status: first.result.status,
        safe_time_s: origin + first.result.safe * duration,
        time_s: origin + first.result.hit * duration,
        collider_ids: [first.a.id, first.b?.id ?? "$ground"],
        shape_ids: [
          ...new Set([...first.a.shapes, ...(first.b?.shapes ?? [])]),
        ],
        unchecked_components: missing,
      };
  }
  return {
    status:
      missing.length ||
      !Object.values(document.entities).some((e) => e.colliders?.length)
        ? "unchecked"
        : "clear",
    safe_time_s: end,
    time_s: end,
    collider_ids: [],
    shape_ids: [],
    unchecked_components: missing,
  };
}

/** Apply the validator's limit consistently to playback, saved cursors and seeks. */
export function clampSceneTime(
  time: number,
  check: MotionCheck,
  duration: number,
): number {
  return Math.max(
    0,
    Math.min(
      time,
      duration,
      check.status === "collision" || check.status === "uncertain"
        ? check.safe_time_s
        : duration,
    ),
  );
}
