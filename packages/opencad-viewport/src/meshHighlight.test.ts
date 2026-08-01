import { describe, expect, it } from "vitest";

import { getMeshMaterialGroups } from "./meshHighlight";

const groups = [
  { start: 0, count: 6, face_index: 0, owner_shape_id: "shape-shank" },
  { start: 6, count: 9, face_index: 1, owner_shape_id: "shape-head" },
  { start: 15, count: 3, face_index: 2, owner_shape_id: "shape-fillet" },
];

describe("mesh feature highlighting", () => {
  it("assigns the highlight material only to faces owned by the selected feature", () => {
    expect(getMeshMaterialGroups(18, groups, "shape-head", true)).toEqual([
      { start: 0, count: 6, materialIndex: 0 },
      { start: 6, count: 9, materialIndex: 1 },
      { start: 15, count: 3, materialIndex: 0 },
    ]);
  });

  it("falls back to whole-body highlighting when provenance is unavailable", () => {
    expect(getMeshMaterialGroups(18, undefined, "shape-head", true)).toEqual([
      { start: 0, count: 18, materialIndex: 1 },
    ]);
  });

  it("falls back to the operation result when it owns no surviving faces", () => {
    expect(getMeshMaterialGroups(18, groups, "shape-union", true)).toEqual([
      { start: 0, count: 18, materialIndex: 1 },
    ]);
  });
});
