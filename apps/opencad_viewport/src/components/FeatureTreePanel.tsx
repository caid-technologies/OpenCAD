import { useEffect, useMemo, useState } from "react";
import type { FeatureNodeView, FeatureTreeView } from "../types";

interface FeatureTreePanelProps {
  tree: FeatureTreeView;
  selectedNodeId?: string | null;
  onSelectNode?: (nodeId: string) => void;
}

const OPERATION_ICONS: Record<string, string> = {
  extrude: "EX",
  boolean_cut: "BC",
  boolean_union: "BU",
  boolean_intersection: "BI",
  fillet: "FL",
  add_sketch: "SK",
  create_sketch: "SK",
  add_cylinder: "CY",
  import_step: "IM",
  import_stl: "IM",
  default: "ND"
};

function opIcon(operation: string): string {
  return OPERATION_ICONS[operation] ?? OPERATION_ICONS.default;
}

export function FeatureTreePanel({ tree, selectedNodeId, onSelectNode }: FeatureTreePanelProps): JSX.Element {
  const { roots, childrenByParent } = useMemo(() => {
    const children: Record<string, string[]> = {};
    Object.keys(tree.nodes).forEach((nodeId) => {
      children[nodeId] = [];
    });

    const rootCandidates: string[] = [];

    Object.entries(tree.nodes).forEach(([nodeId, node]) => {
      if (!node.parent_id) {
        rootCandidates.push(nodeId);
      } else {
        if (!children[node.parent_id]) {
          children[node.parent_id] = [];
        }
        children[node.parent_id].push(nodeId);
      }
    });

    Object.values(children).forEach((ids) => ids.sort());
    rootCandidates.sort();

    return {
      roots: rootCandidates,
      childrenByParent: children
    };
  }, [tree.nodes]);

  const [expanded, setExpanded] = useState<Record<string, boolean>>({ [tree.root_id]: true });

  useEffect(() => {
    if (!selectedNodeId || !tree.nodes[selectedNodeId]) {
      return;
    }

    const toExpand = new Set<string>();
    const visit = (nodeId: string) => {
      if (toExpand.has(nodeId) || !tree.nodes[nodeId]) {
        return;
      }
      toExpand.add(nodeId);
      const parentId = tree.nodes[nodeId].parent_id;
      if (parentId) visit(parentId);
    };

    visit(selectedNodeId);
    setExpanded((current) => {
      const next = { ...current };
      let changed = false;
      toExpand.forEach((nodeId) => {
        if (!next[nodeId]) {
          next[nodeId] = true;
          changed = true;
        }
      });
      return changed ? next : current;
    });
  }, [selectedNodeId, tree.nodes]);

  const toggle = (nodeId: string) => {
    setExpanded((current) => ({ ...current, [nodeId]: !current[nodeId] }));
  };

  const renderNode = (nodeId: string, depth: number): JSX.Element => {
    const node: FeatureNodeView = tree.nodes[nodeId];
    const childIds = childrenByParent[nodeId] ?? [];
    const hasChildren = childIds.length > 0;
    const isExpanded = expanded[nodeId] ?? depth < 1;

    return (
      <div key={nodeId}>
        <div className={`tree-row ${selectedNodeId === nodeId ? "selected" : ""}`} style={{ paddingLeft: `${depth * 14 + 10}px` }}>
          {hasChildren ? (
            <button
              type="button"
              className="tree-toggle"
              aria-label={isExpanded ? "Collapse" : "Expand"}
              onClick={() => toggle(nodeId)}
            >
              {isExpanded ? "-" : "+"}
            </button>
          ) : (
            <span className="tree-spacer" />
          )}
          <span className={`status-dot status-${node.status}`} title={node.status} />
          <span className="op-icon" title={node.operation}>
            {opIcon(node.operation)}
          </span>
          <button type="button" className="tree-node-label" onClick={() => onSelectNode?.(nodeId)}>
            {node.name}
          </button>
        </div>
        {isExpanded ? childIds.map((childId) => renderNode(childId, depth + 1)) : null}
      </div>
    );
  };

  return (
    <aside className="feature-tree-panel">
      <div className="panel-header">Feature Tree</div>
      <div className="panel-body">{roots.map((nodeId) => renderNode(nodeId, 0))}</div>
    </aside>
  );
}
