import { describe, expect, it } from "vitest";

import {
  IDENTITY_RIGID_TRANSFORM,
  normalizeRigidTransform,
  transformsFromJointPoses,
} from "./shapeTransforms";

describe("shape transforms", () => {
  it("uses identity when a transform is absent", () => {
    expect(normalizeRigidTransform(undefined)).toEqual(IDENTITY_RIGID_TRANSFORM);
  });

  it("normalizes quaternions before handing them to Three.js", () => {
    const normalized = normalizeRigidTransform({
      translation_mm: [1, 2, 3],
      rotation_quaternion_xyzw: [0, 0, 2, 2],
    });
    expect(normalized.translation_mm).toEqual([1, 2, 3]);
    expect(normalized.rotation_quaternion_xyzw[0]).toBe(0);
    expect(normalized.rotation_quaternion_xyzw[1]).toBe(0);
    expect(normalized.rotation_quaternion_xyzw[2]).toBeCloseTo(Math.SQRT1_2, 12);
    expect(normalized.rotation_quaternion_xyzw[3]).toBeCloseTo(Math.SQRT1_2, 12);
  });

  it("maps evaluated joint poses by child shape id", () => {
    const transforms = transformsFromJointPoses([
      {
        joint_id: "hinge",
        child_shape_id: "lid",
        progress: 1,
        value: Math.PI / 2,
        unit: "radian",
        transform: {
          translation_mm: [10, -10, 0],
          rotation_quaternion_xyzw: [0, 0, Math.SQRT1_2, Math.SQRT1_2],
        },
      },
    ]);
    expect(transforms.lid.translation_mm).toEqual([10, -10, 0]);
    expect(transforms.lid.rotation_quaternion_xyzw[2]).toBeCloseTo(Math.SQRT1_2, 12);
    expect(transforms.lid.rotation_quaternion_xyzw[3]).toBeCloseTo(Math.SQRT1_2, 12);
  });
});
