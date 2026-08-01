import type { FeatureTreeView } from "./types";
import { isSketchNode } from "./sketchData";

export interface ToolBranchReference {
  referenceId: string;
  rootId: string;
}

export interface FeatureTreeProjection {
  roots: string[];
  sketches: string[];
  childrenByParent: Record<string, string[]>;
  toolBranchesByNode: Record<string, ToolBranchReference[]>;
}

/** Project the dependency graph into a compact, body-oriented feature tree. */
export function projectFeatureTree(tree: FeatureTreeView): FeatureTreeProjection {
  const childrenByParent: Record<string, string[]> = {};
  const toolBranchesByNode: Record<string, ToolBranchReference[]> = {};

  for (const nodeId of Object.keys(tree.nodes)) {
    childrenByParent[nodeId] = [];
    toolBranchesByNode[nodeId] = [];
  }

  const isComponentFeature = (nodeId: string): boolean => {
    const node = tree.nodes[nodeId];
    return Boolean(node) && !isSketchNode(node) && node.operation !== "seed";
  };

  const displayParentByNode: Record<string, string | null> = {};
  for (const [nodeId, node] of Object.entries(tree.nodes)) {
    if (!isComponentFeature(nodeId)) continue;
    let parentId = node.parent_id;
    const visited = new Set<string>([nodeId]);
    while (parentId && tree.nodes[parentId] && !visited.has(parentId)) {
      visited.add(parentId);
      if (isComponentFeature(parentId)) break;
      parentId = tree.nodes[parentId].parent_id;
    }
    const displayParent = parentId && isComponentFeature(parentId) ? parentId : null;
    displayParentByNode[nodeId] = displayParent;
    if (displayParent) childrenByParent[displayParent].push(nodeId);
  }

  const lineageRoot = (startId: string): string => {
    let currentId = startId;
    const visited = new Set<string>();
    while (!visited.has(currentId)) {
      visited.add(currentId);
      const parentId = displayParentByNode[currentId];
      if (!parentId) return currentId;
      currentId = parentId;
    }
    return startId;
  };

  const consumedToolRoots = new Set<string>();
  for (const [nodeId, node] of Object.entries(tree.nodes)) {
    if (!isComponentFeature(nodeId)) continue;
    const consumerRootId = lineageRoot(nodeId);
    const seenRoots = new Set<string>();
    for (const referenceId of node.tool_refs) {
      if (!isComponentFeature(referenceId)) continue;
      const rootId = lineageRoot(referenceId);
      if (seenRoots.has(rootId)) continue;
      seenRoots.add(rootId);
      toolBranchesByNode[nodeId].push({ referenceId, rootId });
      if (rootId !== consumerRootId) consumedToolRoots.add(rootId);
    }
  }

  Object.values(childrenByParent).forEach((ids) => ids.sort());
  Object.values(toolBranchesByNode).forEach((refs) => refs.sort((a, b) =>
    a.rootId.localeCompare(b.rootId),
  ));

  const roots = Object.keys(tree.nodes)
    .filter((nodeId) => isComponentFeature(nodeId) && !displayParentByNode[nodeId])
    .filter((nodeId) => !consumedToolRoots.has(nodeId))
    .sort();
  const sketches = Object.entries(tree.nodes)
    .filter(([, node]) => isSketchNode(node))
    .map(([nodeId]) => nodeId)
    .sort();

  return { roots, sketches, childrenByParent, toolBranchesByNode };
}
