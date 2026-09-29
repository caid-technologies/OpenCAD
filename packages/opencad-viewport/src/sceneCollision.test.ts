import { describe, expect, it } from "vitest";
import { clampSceneTime, validateSceneMotion } from "./sceneCollision";
import { evaluateScene, validateScene } from "./scene";
import type { SceneDocument, SceneEntity } from "./scene";
import type { RigidTransform } from "./types";
import { robotPickPlaceExample } from "./examples/robotPickPlace";
import samples from "./examples/robotPickPlace.states.json";
import legacy from "./examples/robotPickPlaceLegacy.json";
const pose = (x = 0, y = 0, z = 0): RigidTransform => ({
  translation_mm: [x, y, z],
  rotation_quaternion_xyzw: [0, 0, 0, 1],
});
function entity(
  id: string,
  at = pose(),
  size: [number, number, number] = [2, 2, 2],
): SceneEntity {
  return {
    id,
    name: id,
    transform: at,
    interfaces: {},
    assembly: {
      id,
      name: id,
      root_ids: [id],
      metadata: {},
      components: {
        [id]: {
          id,
          name: id,
          child_ids: [],
          geometry_refs: [id],
          feature_refs: [],
          transform: pose(),
          metadata: {},
        },
      },
    },
    colliders: [
      { id: `${id}-body`, component_id: id, size_mm: size, transform: pose() },
    ],
  };
}
function crossing(duration = 1, obstacleX = 0): SceneDocument {
  return {
    version: 1,
    id: "cross",
    name: "Crossing",
    time_s: 0,
    entities: {
      arm: entity("arm", pose(-10), [1, 1, 1]),
      obstacle: entity("obstacle", pose(obstacleX), [0.01, 2, 2]),
    },
    interactions: [
      {
        id: "move",
        actor_id: "arm",
        target_id: "obstacle",
        interaction_type: "MOVE",
        actor_interface: null,
        duration_s: duration,
        actor_pose: pose(10),
        component_poses: {},
        destination_id: null,
      },
    ],
  };
}
function close(a: unknown, b: unknown): void {
  if (typeof b === "number") {
    expect(a).toBeCloseTo(b, 9);
    return;
  }
  if (b && typeof b === "object") {
    expect(Object.keys(a as object)).toEqual(Object.keys(b));
    for (const k of Object.keys(b))
      close(
        (a as Record<string, unknown>)[k],
        (b as Record<string, unknown>)[k],
      );
  } else expect(a).toEqual(b);
}

describe("continuous scene collision validation", () => {
  it("certifies the corrected demo without exclusions and matches Python states", () => {
    const scene = robotPickPlaceExample.document;
    expect(scene.collision_exclusions).toEqual([]);
    expect(validateSceneMotion(scene)).toMatchObject({
      status: "clear",
      safe_time_s: 12,
      unchecked_components: [],
    });
    for (const state of samples)
      close(evaluateScene(scene, state.time_s), state);
    const final = evaluateScene(scene, 12);
    close(final.entity_transforms.box.translation_mm, [0, 24, 8]);
    expect(final.attachments).toEqual({});
    expect(final.placements).toEqual({ box: "table" });
  });
  it("detects a thin obstacle crossed in a millisecond despite clear endpoints", () => {
    const scene = crossing(0.001);
    expect(validateSceneMotion(scene, 0, 0).status).toBe("clear");
    expect(validateSceneMotion(scene, 0.001, 0.001).status).toBe("clear");
    const report = validateSceneMotion(scene, 0, 0.001, {
      time_tolerance_s: 1e-8,
    });
    expect(["collision", "uncertain"]).toContain(report.status);
    expect(report.safe_time_s).toBeGreaterThan(0);
    expect(report.safe_time_s).toBeLessThan(0.0005);
    expect(report.collider_ids.sort()).toEqual(["arm-body", "obstacle-body"]);
    expect(
      validateSceneMotion(scene, 0, report.safe_time_s, {
        time_tolerance_s: 1e-8,
      }).status,
    ).toBe("clear");
  });
  it("fails closed when precision is exhausted", () => {
    const report = validateSceneMotion(crossing(1, -7.543), 0, 1, {
      max_depth: 1,
    });
    expect(report.status).toBe("uncertain");
    expect(report.safe_time_s).toBe(0);
  });
  it("checks rotational sweeps even when the start/end collider poses match", () => {
    const scene = crossing();
    scene.entities.arm.transform = pose();
    scene.entities.obstacle = entity("obstacle", pose(-5));
    const arm = scene.entities.arm;
    arm.assembly.components.root = {
      ...arm.assembly.components.arm,
      id: "root",
      name: "root",
      geometry_refs: [],
      child_ids: ["arm"],
    };
    arm.assembly.root_ids = ["root"];
    arm.colliders![0].transform = pose(5);
    scene.interactions[0].actor_pose = null;
    const halfTurn: RigidTransform = {
      ...pose(),
      rotation_quaternion_xyzw: [0, 0, 1, 0],
    };
    scene.interactions[0].component_poses = { root: halfTurn, arm: halfTurn };
    expect(validateSceneMotion(scene, 0, 0).status).toBe("clear");
    expect(validateSceneMotion(scene, 1, 1).status).toBe("clear");
    expect(["collision", "uncertain"]).toContain(
      validateSceneMotion(scene).status,
    );
  });
  it("allows sliding contact but rejects penetration", () => {
    const scene = crossing();
    scene.entities.arm = entity("arm", pose(2));
    scene.entities.obstacle = entity("obstacle");
    scene.interactions[0].actor_pose = pose(2, 4);
    expect(validateSceneMotion(scene).status).toBe("clear");
    scene.entities.arm.transform = pose(1.9);
    expect(validateSceneMotion(scene).status).toBe("collision");
  });
  it("checks the carried box even when the gripper clears the obstacle", () => {
    const scene = crossing();
    scene.entities.arm = entity("arm", pose(-6, 0, 3), [0.2, 0.2, 0.2]);
    scene.entities.arm.interfaces.grip = {
      id: "grip",
      component_id: "arm",
      transform: pose(0, 0, -3),
    };
    scene.entities.box = entity("box", pose(-6));
    scene.entities.obstacle = entity("obstacle");
    scene.interactions[0].actor_pose = pose(6, 0, 3);
    scene.interactions[0].target_id = "box";
    scene.interactions.unshift({
      ...scene.interactions[0],
      id: "grasp",
      interaction_type: "GRASP",
      actor_interface: "grip",
      duration_s: 0,
      actor_pose: null,
    });
    const report = validateSceneMotion(scene);
    expect(["collision", "uncertain"]).toContain(report.status);
    expect(report.collider_ids.sort()).toEqual(["box-body", "obstacle-body"]);
  });
  it("detects the original unsafe pickup path", () => {
    const scene = JSON.parse(JSON.stringify(legacy.document)) as SceneDocument;
    for (const [id, eid] of [
      ["gripper", "arm"],
      ["box", "box"],
    ]) {
      const vertices = legacy.meshes.find((m) => m.shapeId === id)!.vertices;
      scene.entities[eid].colliders = [];
      for (let i = 0; i < vertices.length; i += 24) {
        const chunk = vertices.slice(i, i + 24);
        const low = [0, 1, 2].map((axis) =>
          Math.min(...chunk.filter((_, index) => index % 3 === axis)),
        );
        const high = [0, 1, 2].map((axis) =>
          Math.max(...chunk.filter((_, index) => index % 3 === axis)),
        );
        scene.entities[eid].colliders!.push({
          id: `${id}-${i}`,
          component_id: id,
          size_mm: high.map((v, j) => v - low[j]) as [number, number, number],
          transform: pose(
            ...(high.map((v, j) => (v + low[j]) / 2) as [
              number,
              number,
              number,
            ]),
          ),
        });
      }
    }
    const report = validateSceneMotion(scene);
    expect(["collision", "uncertain"]).toContain(report.status);
    expect(report.safe_time_s).toBeGreaterThan(1.3);
    expect(report.safe_time_s).toBeLessThan(1.5);
    expect(report.shape_ids.sort()).toEqual(["box", "gripper"]);
    // The same clamp guards playback, seeks, and restored saved cursors.
    expect(clampSceneTime(9, report, 9)).toBe(report.safe_time_s);
    expect(clampSceneTime(0, report, 9)).toBe(0);
  });
  it("reports missing coverage and rejects invalid collider contracts", () => {
    const scene = crossing();
    scene.entities.arm.colliders = [];
    expect(validateSceneMotion(scene)).toMatchObject({
      status: "unchecked",
      unchecked_components: ["arm/arm"],
    });
    const invalid = crossing();
    invalid.entities.arm.colliders![0].size_mm[0] = 0;
    expect(() => validateScene(invalid)).toThrow();
    invalid.entities.arm.colliders![0].size_mm[0] = 1;
    invalid.collision_exclusions = [["missing", "arm-body"]];
    expect(() => validateScene(invalid)).toThrow();
  });
});
