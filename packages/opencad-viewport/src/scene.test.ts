import { describe, expect, it } from "vitest";
import { createScenePlayer, evaluateScene, validateScene } from "./scene";
import type { SceneDocument } from "./scene";
import legacy from "./examples/robotPickPlaceLegacy.json";
import samples from "./examples/robotPickPlaceLegacy.states.json";

const document = legacy.document as unknown as SceneDocument;
function copy(): SceneDocument {
  return JSON.parse(JSON.stringify(document));
}
function close(actual: unknown, expected: unknown): void {
  if (typeof expected === "number") {
    expect(actual).toBeCloseTo(expected, 9);
    return;
  }
  if (expected && typeof expected === "object") {
    expect(Object.keys(actual as object)).toEqual(Object.keys(expected));
    for (const key of Object.keys(expected))
      close(
        (actual as Record<string, unknown>)[key],
        (expected as Record<string, unknown>)[key],
      );
  } else expect(actual).toEqual(expected);
}

describe("scene interactions", () => {
  it("matches Python poses, attachments, and states before/during/after grasp and release", () => {
    const sample = createScenePlayer(document);
    samples.forEach((expected) => close(sample(expected.time_s), expected));
    // Backwards seeking and replay are independent of previous calls.
    close(sample(0), samples[0]);
    close(sample(4), samples[5]);
  });
  it("does not mutate assemblies or leak mutable state between samples", () => {
    const original = JSON.stringify(document);
    const sample = createScenePlayer(document);
    const state = sample(0);
    state.entity_transforms.box.translation_mm[0] = 999;
    expect(sample(0).entity_transforms.box.translation_mm).toEqual([24, 0, 2]);
    expect(JSON.stringify(document)).toBe(original);
  });
  it("preserves the grasp offset as the gripper rotates", () => {
    const scene = copy();
    scene.entities.box.transform.translation_mm = [25, 1, 2];
    close(
      evaluateScene(scene, 2).entity_transforms.box.translation_mm,
      [25, 1, 2],
    );
    close(
      evaluateScene(scene, 5).entity_transforms.box.translation_mm,
      [-1, 25, 10],
    );
  });
  it("RELEASE freezes the object while the arm continues moving", () => {
    const scene = copy();
    scene.interactions[5].interaction_type = "RELEASE";
    scene.interactions[5].destination_id = null;
    const state = evaluateScene(scene, 9);
    expect(state.attachments).toEqual({});
    expect(state.placements).toEqual({});
    close(state.entity_transforms.box.translation_mm, [0, 24, 8]);
  });
  it("supports arbitrary stable IDs, including Object prototype names", () => {
    const scene = JSON.parse(
      JSON.stringify(document).split('"box"').join('"__proto__"'),
    ) as SceneDocument;
    const state = evaluateScene(scene, 4);
    expect(state.attachments["__proto__"].actor_id).toBe("arm");
    close(state.entity_transforms["__proto__"].translation_mm, [
      24 / Math.sqrt(2),
      24 / Math.sqrt(2),
      10,
    ]);
    const missing = copy();
    missing.interactions[1].target_id = "constructor";
    expect(() => validateScene(missing)).toThrow("Invalid interaction entity");
  });
  it("restores the saved cursor through JSON", () => {
    const scene = copy();
    scene.time_s = 4;
    close(evaluateScene(JSON.parse(JSON.stringify(scene))), samples[5]);
  });
  it.each([-1, Infinity, NaN])("rejects invalid time %s", (time) => {
    expect(() => evaluateScene(document, time)).toThrow();
  });
  it("rejects missing references, duplicate ownership, cycles, invalid durations and versions", () => {
    const mutations: Array<(d: SceneDocument) => void> = [
      (d) => {
        d.interactions[1].target_id = "missing";
      },
      (d) => {
        d.interactions[1].actor_interface = "missing";
      },
      (d) => {
        d.interactions[1].actor_interface = null;
      },
      (d) => {
        d.interactions[0].duration_s = 0;
      },
      (d) => {
        d.interactions[0].duration_s = NaN;
      },
      (d) => {
        d.interactions.splice(2, 0, { ...d.interactions[1], id: "again" });
      },
      (d) => {
        d.interactions[5].actor_id = "table";
      },
      (d) => {
        d.interactions[5].destination_id = "missing";
      },
      (d) => {
        d.entities.arm.assembly.components.gripper.child_ids = ["base"];
      },
      (d) => {
        d.entities.table.assembly.components.table.geometry_refs = ["box"];
      },
      (d) => {
        d.version = 2 as 1;
      },
      (d) => {
        d.entities.box.interfaces.top = {
          id: "top",
          component_id: "box",
          transform: d.entities.box.transform,
        };
        d.interactions.splice(2, 0, {
          ...d.interactions[1],
          id: "cycle",
          actor_id: "box",
          target_id: "arm",
          actor_interface: "top",
        });
      },
    ];
    for (const mutate of mutations) {
      const scene = copy();
      mutate(scene);
      expect(() => validateScene(scene)).toThrow();
    }
  });
});
