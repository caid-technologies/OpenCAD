import { describe, expect, it } from "vitest";

import { projectFeatureTree } from "./featureTreeProjection";
import type { FeatureNodeView, FeatureTreeView } from "./types";

function node(
  id: string,
  parentId: string | null = null,
  toolRefs: string[] = [],
  overrides: Partial<FeatureNodeView> = {},
): FeatureNodeView {
  return {
    id,
    name: id,
    operation: "feature",
    parameters: {},
    typed_parameters: {},
    parameter_bindings: [],
    parent_id: parentId,
    tool_refs: toolRefs,
    depends_on: [...(parentId ? [parentId] : []), ...toolRefs],
    shape_id: `shape-${id}`,
    status: "built",
    suppressed: false,
    ...overrides,
  };
}

function tree(nodes: FeatureNodeView[]): FeatureTreeView {
  return {
    nodes: Object.fromEntries(nodes.map((item) => [item.id, item])),
    root_id: nodes[0]?.id ?? "root",
    active_branch: "main",
    revision: 1,
  };
}

describe("feature tree projection", () => {
  it("nests a consumed tool branch under its boolean operation", () => {
    const projection = projectFeatureTree(tree([
      node("cube"),
      node("cut", "cube", ["sphere"]),
      node("sphere"),
    ]));

    expect(projection.roots).toEqual(["cube"]);
    expect(projection.sketches).toEqual([]);
    expect(projection.childrenByParent.cube).toEqual(["cut"]);
    expect(projection.toolBranchesByNode.cut).toEqual([
      { referenceId: "sphere", rootId: "sphere" },
    ]);
  });

  it("moves an entire tool feature chain instead of leaving its root behind", () => {
    const projection = projectFeatureTree(tree([
      node("body"),
      node("cut", "body", ["tool-fillet"]),
      node("tool-base"),
      node("tool-fillet", "tool-base"),
    ]));

    expect(projection.roots).toEqual(["body"]);
    expect(projection.toolBranchesByNode.cut[0]).toEqual({
      referenceId: "tool-fillet",
      rootId: "tool-base",
    });
  });

  it("does not hide the body when a feature references its own lineage", () => {
    const projection = projectFeatureTree(tree([
      node("body"),
      node("feature", "body", ["body"]),
    ]));

    expect(projection.roots).toEqual(["body"]);
  });

  it("separates sketches and promotes their consuming extrusion to a component root", () => {
    const projection = projectFeatureTree(tree([
      node("root", null, [], { operation: "seed", shape_id: null }),
      node("profile", "root", [], { operation: "create_sketch", sketch_id: "profile" }),
      node("body", "profile", [], { operation: "extrude", sketch_id: "profile" }),
      node("fillet", "body"),
    ]));

    expect(projection.sketches).toEqual(["profile"]);
    expect(projection.roots).toEqual(["body"]);
    expect(projection.childrenByParent.body).toEqual(["fillet"]);
    expect(projection.childrenByParent.profile).toEqual([]);
  });
});
