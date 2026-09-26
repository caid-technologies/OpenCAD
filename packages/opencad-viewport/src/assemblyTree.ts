import type { AssemblyTreeView } from "./types";

/** Return a component and its descendants in stable depth-first tree order. */
export function getAssemblyComponentIds(
  tree: AssemblyTreeView,
  componentId: string,
  includeSelf = true,
): string[] {
  if (!tree.components[componentId]) {
    return [];
  }

  const ordered: string[] = [];
  const visited = new Set<string>();

  const walk = (currentId: string): void => {
    if (visited.has(currentId)) {
      return;
    }
    const component = tree.components[currentId];
    if (!component) {
      return;
    }
    visited.add(currentId);
    ordered.push(currentId);
    component.child_ids.forEach(walk);
  };

  walk(componentId);
  return includeSelf ? ordered : ordered.slice(1);
}

/** Resolve all unique geometry refs selected by a semantic assembly component. */
export function getAssemblyGeometryRefs(
  tree: AssemblyTreeView,
  componentId: string,
  includeDescendants = true,
): string[] {
  const componentIds = includeDescendants
    ? getAssemblyComponentIds(tree, componentId)
    : tree.components[componentId]
      ? [componentId]
      : [];

  const refs: string[] = [];
  const seen = new Set<string>();
  for (const currentId of componentIds) {
    for (const geometryRef of tree.components[currentId].geometry_refs) {
      if (!seen.has(geometryRef)) {
        seen.add(geometryRef);
        refs.push(geometryRef);
      }
    }
  }
  return refs;
}

/** Build a child-to-parent index for expanding selected component ancestry. */
export function getAssemblyParents(tree: AssemblyTreeView): Record<string, string> {
  const parentByChild: Record<string, string> = {};
  for (const component of Object.values(tree.components)) {
    for (const childId of component.child_ids) {
      parentByChild[childId] = component.id;
    }
  }
  return parentByChild;
}
