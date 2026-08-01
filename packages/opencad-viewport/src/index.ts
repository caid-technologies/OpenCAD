/**
 * Public API of the OpenCAD viewport component library.
 *
 * Consumers import components and helpers from here. The stylesheet is not
 * imported by this module so that it stays opt-in — bring it in explicitly:
 *
 *   import "opencad-viewport/styles.css";
 */

// ── Components ──────────────────────────────────────────────────────

export { CadFileToolbar } from "./components/CadFileToolbar";
export { ChatPanel } from "./components/ChatPanel";
export { FeatureTreePanel } from "./components/FeatureTreePanel";
export { SketchEditor } from "./components/SketchEditor";
export { Viewport3D } from "./components/Viewport3D";

// ── API client ──────────────────────────────────────────────────────

export { OpenCadApiClient } from "./api/client";
export type { MeshStreamChunk } from "./api/client";

// ── Feature-tree helpers ────────────────────────────────────────────

export { projectFeatureTree } from "./featureTreeProjection";
export type { FeatureTreeProjection, ToolBranchReference } from "./featureTreeProjection";
export { getHighlightedViewportShapeIds, getViewportShapeIds } from "./featureVisibility";
export { getMeshMaterialGroups } from "./meshHighlight";
export type { MeshMaterialGroup } from "./meshHighlight";
export { sketchFromNode } from "./sketchData";

// ── Mock fixtures (useful for tests, stories, and offline development) ──

export { mockChat, mockFeatureTree, mockMeshes, mockSketch, mockSolveSketch } from "./mock/mockData";

// ── Types ───────────────────────────────────────────────────────────

export { createEmptySketch, createEmptyTree } from "./types";
export type {
  CadFileFormat,
  CadImportResult,
  ChatHistoryItem,
  ChatOperationExecution,
  ChatRequestPayload,
  ChatResponsePayload,
  ChatRole,
  FeatureNodeStatus,
  FeatureNodeView,
  FeatureTreeView,
  MeshFaceGroup,
  MeshPayload,
  ParameterBinding,
  ParameterType,
  SketchArc,
  SketchCircle,
  SketchConstraint,
  SketchEntity,
  SketchLine,
  SketchPayload,
  SketchPoint,
  SketchRectangle,
  SolverResult,
  TreeSnapshotPayload,
  TypedParameter,
} from "./types";
