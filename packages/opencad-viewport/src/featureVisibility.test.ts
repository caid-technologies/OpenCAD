import { describe, expect, it } from "vitest";

import { getHighlightedViewportShapeIds, getViewportShapeIds } from "./featureVisibility";
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

describe("viewport feature visibility", () => {
  it("renders only the terminal result of a feature and tool chain", () => {
    const screw = tree([
      node("shank"),
      node("head"),
      node("body", "shank", ["head"]),
      node("relief", "body"),
    ]);

    expect([...getViewportShapeIds(screw)]).toEqual(["shape-relief"]);
  });

  it("keeps independent terminal bodies visible", () => {
    const assembly = tree([
      node("base"),
      node("fillet", "base"),
      node("imported"),
    ]);

    expect([...getViewportShapeIds(assembly)]).toEqual(["shape-fillet", "shape-imported"]);
  });

  it("leaves the last successful body visible when a downstream feature is not built", () => {
    const model = tree([
      node("base"),
      node("failed-cut", "base", [], { status: "failed", shape_id: null }),
    ]);

    expect([...getViewportShapeIds(model)]).toEqual(["shape-base"]);
  });

  it("highlights the current output for a selected historical input", () => {
    const screw = tree([
      node("shank"),
      node("head"),
      node("body", "shank", ["head"]),
      node("relief", "body"),
      node("independent"),
    ]);
    const visible = getViewportShapeIds(screw);

    expect([...getHighlightedViewportShapeIds(screw, "shank", visible)]).toEqual(["shape-relief"]);
    expect([...getHighlightedViewportShapeIds(screw, "head", visible)]).toEqual(["shape-relief"]);
    expect([...getHighlightedViewportShapeIds(screw, "independent", visible)]).toEqual(["shape-independent"]);
  });

  it("renders the component rather than its consumed sketch mesh", () => {
    const model = tree([
      node("profile", null, [], { operation: "create_sketch", sketch_id: "profile" }),
      node("body", null, [], {
        operation: "extrude",
        sketch_id: "profile",
        depends_on: ["profile"],
      }),
    ]);

    expect([...getViewportShapeIds(model)]).toEqual(["shape-body"]);
  });
});
