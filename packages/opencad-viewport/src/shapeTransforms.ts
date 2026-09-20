import type { JointPose, RigidTransform } from "./types";

export const IDENTITY_RIGID_TRANSFORM: RigidTransform = {
  translation_mm: [0, 0, 0],
  rotation_quaternion_xyzw: [0, 0, 0, 1],
};

export function normalizeRigidTransform(
  transform: RigidTransform | null | undefined,
): RigidTransform {
  if (!transform) return IDENTITY_RIGID_TRANSFORM;

  const translation = transform.translation_mm ?? [0, 0, 0];
  const quaternion = normalizeQuaternion(
    transform.rotation_quaternion_xyzw ?? [0, 0, 0, 1],
  );

  return {
    translation_mm: [
      finite(translation[0], 0),
      finite(translation[1], 0),
      finite(translation[2], 0),
    ],
    rotation_quaternion_xyzw: quaternion,
  };
}

export function transformsFromJointPoses(
  poses: readonly JointPose[],
): Record<string, RigidTransform> {
  const transforms: Record<string, RigidTransform> = {};
  for (const pose of poses) {
    if (!pose?.child_shape_id) continue;
    transforms[pose.child_shape_id] = normalizeRigidTransform(pose.transform);
  }
  return transforms;
}

function normalizeQuaternion(
  value: readonly number[],
): [number, number, number, number] {
  const raw: [number, number, number, number] = [
    finite(value[0], 0),
    finite(value[1], 0),
    finite(value[2], 0),
    finite(value[3], 1),
  ];
  const length = Math.hypot(...raw);
  if (length < 1e-12) return [0, 0, 0, 1];
  return raw.map((component) => component / length) as [number, number, number, number];
}

function finite(value: number | undefined, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
