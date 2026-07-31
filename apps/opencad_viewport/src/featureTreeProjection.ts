import type { FeatureTreeView } from "./types";

export interface ToolBranchReference {
  referenceId: string;
  rootId: string;
}

export interface FeatureTreeProjection {
  roots: string[];
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

  for (const [nodeId, node] of Object.entries(tree.nodes)) {
    if (node.parent_id && tree.nodes[node.parent_id]) {
      childrenByParent[node.parent_id].push(nodeId);
    }
  }

  const lineageRoot = (startId: string): string => {
    let currentId = startId;
    const visited = new Set<string>();
    while (!visited.has(currentId)) {
      visited.add(currentId);
      const parentId = tree.nodes[currentId]?.parent_id;
      if (!parentId || !tree.nodes[parentId]) return currentId;
      currentId = parentId;
    }
    return startId;
  };

  const consumedToolRoots = new Set<string>();
  for (const [nodeId, node] of Object.entries(tree.nodes)) {
    const consumerRootId = lineageRoot(nodeId);
    const seenRoots = new Set<string>();
    for (const referenceId of node.tool_refs) {
      if (!tree.nodes[referenceId]) continue;
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

  const roots = Object.entries(tree.nodes)
    .filter(([, node]) => !node.parent_id || !tree.nodes[node.parent_id])
    .map(([nodeId]) => nodeId)
    .filter((nodeId) => !consumedToolRoots.has(nodeId))
    .sort();

  return { roots, childrenByParent, toolBranchesByNode };
}
