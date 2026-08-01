import { describe, expect, it } from "vitest";

import { isSketchNode, sketchFromNode } from "./sketchData";
import type { FeatureNodeView } from "./types";

function node(overrides: Partial<FeatureNodeView> = {}): FeatureNodeView {
  return {
    id: "sketch-1",
    name: "Profile",
    operation: "create_sketch",
    parameters: {},
    typed_parameters: {},
    parameter_bindings: [],
    sketch_id: "sketch-1",
    parent_id: null,
    tool_refs: [],
    depends_on: [],
    shape_id: "shape-1",
    status: "built",
    suppressed: false,
    ...overrides,
  };
}

describe("sketch tree data", () => {
  it("recognizes only nodes that own a sketch", () => {
    expect(isSketchNode(node())).toBe(true);
    expect(isSketchNode(node({ operation: "add_sketch" }))).toBe(true);
    expect(isSketchNode(node({ id: "extrude-1", operation: "extrude", sketch_id: "sketch-1" }))).toBe(false);
  });

  it("normalizes fluent line and circle coordinates for the solver", () => {
    const sketch = sketchFromNode(node({
      parameters: {
        entities: {
          l1: { id: "l1", type: "line", start: [1, 2], end: [3, 4] },
          c1: { id: "c1", type: "circle", center: [5, 6], radius: 2 },
        },
        constraints: [{ id: "h1", type: "horizontal", a: "l1" }],
      },
    }));

    expect(sketch).toEqual({
      entities: {
        l1: { id: "l1", type: "line", x1: 1, y1: 2, x2: 3, y2: 4 },
        c1: { id: "c1", type: "circle", cx: 5, cy: 6, radius: 2 },
      },
      constraints: [{ id: "h1", type: "horizontal", a: "l1" }],
    });
  });

  it("does not open an empty editor for malformed sketch data", () => {
    expect(sketchFromNode(node({ parameters: {} }))).toBeNull();
  });
});
