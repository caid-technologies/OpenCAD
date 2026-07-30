export type FeatureNodeStatus = "pending" | "built" | "failed" | "stale" | "suppressed";

export type ParameterType = "int" | "float" | "bool" | "string" | "shape_ref" | "json";

export interface TypedParameter {
  type: ParameterType;
  value: unknown;
}

export interface ParameterBinding {
  parameter: string;
  source: "solver" | "node";
  source_key: string;
  source_path: string;
  cast_as?: ParameterType | null;
  expression?: string | null;
}

export interface FeatureNodeView {
  id: string;
  name: string;
  operation: string;
  parameters: Record<string, unknown>;
  typed_parameters: Record<string, TypedParameter>;
  parameter_bindings: ParameterBinding[];
  sketch_id?: string | null;
  parent_id: string | null;
  tool_refs: string[];
  depends_on: string[];
  shape_id?: string | null;
  status: FeatureNodeStatus;
  suppressed: boolean;
}

export interface FeatureTreeView {
  nodes: Record<string, FeatureNodeView>;
  root_id: string;
  active_branch: string;
  revision: number;
}

export function createEmptyTree(): FeatureTreeView {
  return {
    root_id: "root",
    active_branch: "main",
    revision: 0,
    nodes: {
    },
  };
}

export interface MeshPayload {
  shapeId: string;
  vertices: number[] | Float32Array;
  faces: number[] | Uint32Array;
  normals?: number[] | Float32Array;
  name?: string;
}

export interface SketchPoint {
  id: string;
  type: "point";
  x: number;
  y: number;
}

export interface SketchLine {
  id: string;
  type: "line";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface SketchCircle {
  id: string;
  type: "circle";
  cx: number;
  cy: number;
  radius: number;
}

export interface SketchArc {
  id: string;
  type: "arc";
  cx: number;
  cy: number;
  radius: number;
  start_angle: number;
  end_angle: number;
}

export interface SketchRectangle {
  id: string;
  type: "rectangle";
  x: number;
  y: number;
  width: number;
  height: number;
}

export type SketchEntity = SketchPoint | SketchLine | SketchCircle | SketchArc | SketchRectangle;

export interface SketchConstraint {
  id: string;
  type: string;
  a: string;
  b?: string;
  value?: number;
}

export interface SketchPayload {
  entities: Record<string, SketchEntity>;
  constraints: SketchConstraint[];
}

export function createEmptySketch(): SketchPayload {
  return { entities: {}, constraints: [] };
}

export interface SolverResult {
  status: "SOLVED" | "OVERCONSTRAINED" | "UNDERCONSTRAINED";
  sketch: SketchPayload;
  conflict_constraint_id?: string | null;
  max_residual?: number;
  message?: string;
}

export interface ChatOperationExecution {
  tool: string;
  status: "ok" | "error";
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
}

export type ChatRole = "system" | "user" | "assistant";

export interface ChatHistoryItem {
  role: ChatRole;
  content: string;
}

export interface ChatRequestPayload {
  message: string;
  tree_state: FeatureTreeView;
  conversation_history: ChatHistoryItem[];
  reasoning?: boolean;
  llm_provider?: string;
  llm_model?: string;
  generate_code?: boolean;
}

export interface ChatResponsePayload {
  response: string;
  operations_executed: ChatOperationExecution[];
  new_tree_state: FeatureTreeView;
}

export interface TreeSnapshotPayload {
  version: number;
  created_at: string;
  tree: FeatureTreeView;
}
