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
export { ComponentTreePanel } from "./components/ComponentTreePanel";
export { FeatureTreePanel } from "./components/FeatureTreePanel";
export { SketchEditor } from "./components/SketchEditor";
export { Viewport3D } from "./components/Viewport3D";

// ── API client ──────────────────────────────────────────────────────

export { OpenCadApiClient } from "./api/client";
export type { MeshStreamChunk } from "./api/client";

// ── Feature-tree helpers ────────────────────────────────────────────

export { getAssemblyComponentIds, getAssemblyGeometryRefs, getAssemblyParents } from "./assemblyTree";
export { projectFeatureTree } from "./featureTreeProjection";
export type { FeatureTreeProjection, ToolBranchReference } from "./featureTreeProjection";
export { getHighlightedViewportShapeIds, getViewportShapeIds } from "./featureVisibility";
export { getMeshMaterialGroups } from "./meshHighlight";
export { IDENTITY_RIGID_TRANSFORM, normalizeRigidTransform, transformsFromJointPoses } from "./shapeTransforms";
export type { MeshMaterialGroup } from "./meshHighlight";
export { sketchFromNode } from "./sketchData";

// ── Mock fixtures (useful for tests, stories, and offline development) ──

export { mockChat, mockFeatureTree, mockMeshes, mockSketch, mockSolveSketch } from "./mock/mockData";

// ── Types ───────────────────────────────────────────────────────────

export { createEmptyAssemblyTree, createEmptySketch, createEmptyTree } from "./types";
export type {
  AssemblyComponentView,
  AssemblyTreeView,
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
  CreateKinematicJointInput,
  JointPose,
  JointUnit,
  KinematicJoint,
  KinematicJointType,
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
  RigidTransform,
  SolverResult,
  TreeSnapshotPayload,
  TypedParameter,
} from "./types";

// Independent scenes and temporary interaction relationships.
export { ScenePlayer } from "./components/ScenePlayer";
export type { ScenePlayerProps } from "./components/ScenePlayer";
export { createScenePlayer, evaluateScene, sceneDuration, validateScene } from "./scene";
export type { Attachment, Interaction, SceneDocument, SceneEntity, SceneInterface, SceneState } from "./scene";
export { robotPickPlaceExample } from "./examples/robotPickPlace";

export { validateSceneMotion, clampSceneTime } from "./sceneCollision";
export type { MotionCheck, CollisionOptions } from "./sceneCollision";
export type { SceneCollider } from "./scene";
