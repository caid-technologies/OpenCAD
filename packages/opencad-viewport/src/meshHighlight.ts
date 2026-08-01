import type { MeshFaceGroup } from "./types";

export interface MeshMaterialGroup {
  start: number;
  count: number;
  materialIndex: 0 | 1;
}

/** Build Three.js draw groups without duplicating any triangle geometry. */
export function getMeshMaterialGroups(
  indexCount: number,
  faceGroups: MeshFaceGroup[] | undefined,
  selectedOwnerShapeId: string | null | undefined,
  wholeMeshSelected: boolean,
): MeshMaterialGroup[] {
  const validGroups = (faceGroups ?? []).filter(
    (group) => group.start >= 0 && group.count > 0 && group.start + group.count <= indexCount,
  );
  const hasSelectedOwner = Boolean(selectedOwnerShapeId) && validGroups.some(
    (group) => group.owner_shape_id === selectedOwnerShapeId,
  );

  if (!hasSelectedOwner || validGroups.length === 0) {
    return indexCount > 0
      ? [{ start: 0, count: indexCount, materialIndex: wholeMeshSelected ? 1 : 0 }]
      : [];
  }

  return validGroups.map((group) => ({
    start: group.start,
    count: group.count,
    materialIndex: group.owner_shape_id === selectedOwnerShapeId ? 1 : 0,
  }));
}
