import type { FeatureNodeView, FeatureTreeView } from "./types";

function isRenderable(node: FeatureNodeView): boolean {
  return node.status === "built" && !node.suppressed && Boolean(node.shape_id);
}

function dependencies(node: FeatureNodeView): string[] {
  return Array.from(new Set([
    ...(node.parent_id ? [node.parent_id] : []),
    ...node.tool_refs,
    ...node.depends_on,
  ]));
}

/**
 * Return the current body outputs for the viewport.
 *
 * Feature nodes retain the shape produced at every modeling step. A shape is
 * historical once another built feature consumes it as a parent or tool, so
 * drawing both shapes would put duplicate faces at the same coordinates.
 */
export function getViewportShapeIds(tree: FeatureTreeView): Set<string> {
  const renderableEntries = Object.entries(tree.nodes).filter(([, node]) => isRenderable(node));
  const consumedNodeIds = new Set<string>();

  for (const [, node] of renderableEntries) {
    for (const dependencyId of dependencies(node)) {
      if (tree.nodes[dependencyId] && isRenderable(tree.nodes[dependencyId])) {
        consumedNodeIds.add(dependencyId);
      }
    }
  }

  return new Set(
    renderableEntries
      .filter(([nodeId]) => !consumedNodeIds.has(nodeId))
      .map(([, node]) => node.shape_id as string),
  );
}

/** Map a historical feature selection onto the current body output(s). */
export function getHighlightedViewportShapeIds(
  tree: FeatureTreeView,
  selectedNodeId: string | null | undefined,
  viewportShapeIds: ReadonlySet<string> = getViewportShapeIds(tree),
): Set<string> {
  if (!selectedNodeId || !tree.nodes[selectedNodeId]) {
    return new Set();
  }

  const reachesSelection = (nodeId: string, visited: Set<string>): boolean => {
    if (nodeId === selectedNodeId) return true;
    if (visited.has(nodeId)) return false;
    visited.add(nodeId);

    const node = tree.nodes[nodeId];
    return Boolean(node) && dependencies(node).some((dependencyId) =>
      reachesSelection(dependencyId, visited),
    );
  };

  return new Set(
    Object.entries(tree.nodes)
      .filter(([, node]) => Boolean(node.shape_id) && viewportShapeIds.has(node.shape_id as string))
      .filter(([nodeId]) => reachesSelection(nodeId, new Set()))
      .map(([, node]) => node.shape_id as string),
  );
}
