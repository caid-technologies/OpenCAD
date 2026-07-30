import type {
  ChatOperationExecution,
  FeatureTreeView,
  MeshPayload,
  SketchPayload,
  SolverResult
} from "../types";

const vertices = [
  -20, -12, 0,
  20, -12, 0,
  20, 12, 0,
  -20, 12, 0,
  -20, -12, 8,
  20, -12, 8,
  20, 12, 8,
  -20, 12, 8
];

const faces = [
  // bottom (z=0, normal -Z)
  0, 3, 2,
  0, 2, 1,
  // top (z=8, normal +Z)
  4, 5, 6,
  4, 6, 7,
  // front (y=-12, normal -Y)
  0, 1, 5,
  0, 5, 4,
  // right (x=+20, normal +X)
  1, 2, 6,
  1, 6, 5,
  // back (y=+12, normal +Y)
  2, 3, 7,
  2, 7, 6,
  // left (x=-20, normal -X)
  3, 0, 4,
  3, 4, 7,
];

export const mockMeshes: MeshPayload[] = [
  {
    shapeId: "shape-base-plate",
    name: "Base Plate",
    vertices,
    faces
  },
  {
    shapeId: "shape-cutout-tool",
    name: "Cutout Tool",
    vertices: vertices.map((value, index) => {
      if (index % 3 === 0) {
        return value * 0.4;
      }
      if (index % 3 === 1) {
        return value * 0.3;
      }
      return value + 9;
    }),
    faces
  }
];

export const mockFeatureTree: FeatureTreeView = {
  root_id: "base",
  active_branch: "main",
  revision: 1,
  nodes: {
    base: {
      id: "base",
      name: "Base",
      operation: "extrude",
      parameters: { depth: 8 },
      typed_parameters: {},
      parameter_bindings: [],
      sketch_id: "sketch-base",
      parent_id: null,
      tool_refs: [],
      depends_on: [],
      shape_id: "shape-base-plate",
      status: "built",
      suppressed: false
    },
    cutout: {
      id: "cutout",
      name: "Center Cutout",
      operation: "boolean_cut",
      parameters: { tool: "cutout-tool" },
      typed_parameters: {},
      parameter_bindings: [],
      parent_id: "base",
      tool_refs: ["cutout-tool"],
      depends_on: ["base"],
      shape_id: "shape-cutout",
      status: "stale",
      suppressed: false
    },
    fillet: {
      id: "fillet",
      name: "Edge Fillet",
      operation: "fillet",
      parameters: { radius: 1.5 },
      typed_parameters: {},
      parameter_bindings: [],
      parent_id: "cutout",
      tool_refs: [],
      depends_on: ["cutout"],
      shape_id: null,
      status: "pending",
      suppressed: false
    }
  }
};

export const mockSketch: SketchPayload = {
  entities: {
    p1: { id: "p1", type: "point", x: -20, y: -12 },
    p2: { id: "p2", type: "point", x: 20, y: -12 },
    p3: { id: "p3", type: "point", x: 20, y: 12 },
    p4: { id: "p4", type: "point", x: -20, y: 12 },
    l1: { id: "l1", type: "line", x1: -20, y1: -12, x2: 20, y2: -12 },
    l2: { id: "l2", type: "line", x1: 20, y1: -12, x2: 20, y2: 12 },
    c1: { id: "c1", type: "circle", cx: 0, cy: 0, radius: 6 }
  },
  constraints: [
    { id: "h1", type: "horizontal", a: "l1" },
    { id: "v1", type: "vertical", a: "l2" },
    { id: "d1", type: "distance", a: "p1", b: "p2", value: 40 }
  ]
};

export async function mockSolveSketch(sketch: SketchPayload): Promise<SolverResult> {
  return {
    status: "UNDERCONSTRAINED",
    sketch,
    max_residual: 0.0003,
    message: "Mock solver: constraints evaluated."
  };
}

export async function mockChat(message: string): Promise<{ response: string; operations: ChatOperationExecution[] }> {
  const operations: ChatOperationExecution[] = [
    {
      tool: "add_sketch",
      status: "ok",
      arguments: { name: "Base Profile" },
      result: { sketch_id: "sketch-1001" }
    },
    {
      tool: "extrude",
      status: "ok",
      arguments: { sketch_id: "sketch-1001", depth: 8, name: "Base Plate" },
      result: { feature_id: "feat-1002" }
    },
    {
      tool: "boolean_cut",
      status: "ok",
      arguments: { base_id: "feat-1002", tool_id: "feat-1003", name: "Center Cutout" },
      result: { feature_id: "feat-1004" }
    }
  ];

  return {
    response: `Mock agent response to: \"${message}\". Completed requested feature updates.`,
    operations
  };
}
