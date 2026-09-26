import { useEffect, useMemo, useState } from "react";

import { getAssemblyGeometryRefs, getAssemblyParents } from "../assemblyTree";
import type { AssemblyTreeView } from "../types";

interface ComponentTreePanelProps {
  tree: AssemblyTreeView;
  selectedComponentId?: string | null;
  onSelectComponent?: (componentId: string, geometryRefs: string[]) => void;
}

/**
 * Render OpenCAD's semantic assembly hierarchy independently from feature history.
 *
 * Selecting an assembly node reports every geometry reference owned by that node
 * and its descendants so callers can highlight the corresponding viewport shapes.
 */
export function ComponentTreePanel({
  tree,
  selectedComponentId,
  onSelectComponent,
}: ComponentTreePanelProps): JSX.Element {
  const parentByChild = useMemo(() => getAssemblyParents(tree), [tree]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>(
    Object.fromEntries(tree.root_ids.map((rootId) => [rootId, true])),
  );

  useEffect(() => {
    if (!selectedComponentId || !tree.components[selectedComponentId]) {
      return;
    }

    const toExpand = new Set<string>();
    let currentId: string | undefined = selectedComponentId;
    while (currentId && !toExpand.has(currentId)) {
      toExpand.add(currentId);
      currentId = parentByChild[currentId];
    }

    setExpanded((current) => {
      const next = { ...current };
      let changed = false;
      for (const componentId of toExpand) {
        if (!next[componentId]) {
          next[componentId] = true;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [parentByChild, selectedComponentId, tree.components]);

  const toggle = (componentId: string): void => {
    setExpanded((current) => ({
      ...current,
      [componentId]: !current[componentId],
    }));
  };

  const renderNode = (
    componentId: string,
    depth: number,
    ancestry: Set<string>,
  ): JSX.Element | null => {
    const component = tree.components[componentId];
    if (!component) {
      return null;
    }

    const cycle = ancestry.has(componentId);
    const childIds = cycle ? [] : component.child_ids.filter((childId) => Boolean(tree.components[childId]));
    const hasChildren = childIds.length > 0;
    const isExpanded = expanded[componentId] ?? depth === 0;
    const nextAncestry = new Set(ancestry);
    nextAncestry.add(componentId);

    return (
      <div key={componentId}>
        <div
          className={`tree-row ${selectedComponentId === componentId ? "selected" : ""}`}
          style={{ paddingLeft: `${depth * 14 + 10}px` }}
        >
          {hasChildren ? (
            <button
              type="button"
              className="tree-toggle"
              aria-label={isExpanded ? "Collapse" : "Expand"}
              onClick={() => toggle(componentId)}
            >
              {isExpanded ? "-" : "+"}
            </button>
          ) : (
            <span className="tree-spacer" />
          )}
          <span
            className="op-icon"
            title={hasChildren ? "Assembly" : "Component"}
          >
            {hasChildren ? "AS" : "CP"}
          </span>
          <button
            type="button"
            className="tree-node-label"
            onClick={() => onSelectComponent?.(
              componentId,
              getAssemblyGeometryRefs(tree, componentId),
            )}
          >
            {component.name}
          </button>
          {component.geometry_refs.length > 0 ? (
            <span
              className="tree-section-count"
              title={`${component.geometry_refs.length} direct geometry reference(s)`}
            >
              {component.geometry_refs.length}
            </span>
          ) : null}
        </div>
        {isExpanded
          ? childIds.map((childId) => renderNode(childId, depth + 1, nextAncestry))
          : null}
      </div>
    );
  };

  return (
    <aside className="component-tree-panel">
      <div className="panel-header">Component Tree</div>
      <div className="panel-body">
        {tree.root_ids.length > 0 ? (
          tree.root_ids.map((rootId) => renderNode(rootId, 0, new Set<string>()))
        ) : (
          <div className="tree-empty">No assembly components</div>
        )}
      </div>
    </aside>
  );
}
