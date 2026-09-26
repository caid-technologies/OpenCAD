import { describe, expect, it } from "vitest";

import {
  getAssemblyComponentIds,
  getAssemblyGeometryRefs,
  getAssemblyParents,
} from "./assemblyTree";
import type { AssemblyTreeView } from "./types";

const tree: AssemblyTreeView = {
  id: "micro-arm",
  name: "Micro Arm",
  root_ids: ["micro-arm"],
  metadata: {},
  components: {
    "micro-arm": {
      id: "micro-arm",
      name: "Micro Arm",
      child_ids: ["base", "shoulder"],
      geometry_refs: [],
      feature_refs: [],
      metadata: {},
    },
    base: {
      id: "base",
      name: "Base",
      child_ids: [],
      geometry_refs: ["shape-base"],
      feature_refs: [],
      metadata: {},
    },
    shoulder: {
      id: "shoulder",
      name: "Shoulder",
      child_ids: ["servo", "upper-arm"],
      geometry_refs: [],
      feature_refs: [],
      metadata: {},
    },
    servo: {
      id: "servo",
      name: "Servo",
      child_ids: [],
      geometry_refs: ["shape-servo"],
      feature_refs: [],
      metadata: {},
    },
    "upper-arm": {
      id: "upper-arm",
      name: "Upper Arm",
      child_ids: [],
      geometry_refs: ["shape-upper-arm"],
      feature_refs: ["extrude-19"],
      metadata: { source_id: "link_upper_arm" },
    },
  },
};

describe("assembly tree helpers", () => {
  it("walks semantic descendants independently from feature history", () => {
    expect(getAssemblyComponentIds(tree, "shoulder")).toEqual([
      "shoulder",
      "servo",
      "upper-arm",
    ]);
  });

  it("resolves geometry for component selection", () => {
    expect(getAssemblyGeometryRefs(tree, "shoulder")).toEqual([
      "shape-servo",
      "shape-upper-arm",
    ]);
    expect(getAssemblyGeometryRefs(tree, "shoulder", false)).toEqual([]);
  });

  it("builds the ancestry index used by the component panel", () => {
    expect(getAssemblyParents(tree)).toMatchObject({
      base: "micro-arm",
      shoulder: "micro-arm",
      servo: "shoulder",
      "upper-arm": "shoulder",
    });
  });
});
