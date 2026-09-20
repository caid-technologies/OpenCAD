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
    expect(
      normalizeRigidTransform({
        translation_mm: [1, 2, 3],
        rotation_quaternion_xyzw: [0, 0, 2, 2],
      }),
    ).toEqual({
      translation_mm: [1, 2, 3],
      rotation_quaternion_xyzw: [0, 0, Math.SQRT1_2, Math.SQRT1_2],
    });
  });

  it("maps evaluated joint poses by child shape id", () => {
    expect(
      transformsFromJointPoses([
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
      ]),
    ).toEqual({
      lid: {
        translation_mm: [10, -10, 0],
        rotation_quaternion_xyzw: [0, 0, Math.SQRT1_2, Math.SQRT1_2],
      },
    });
  });
});
