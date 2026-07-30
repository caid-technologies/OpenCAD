import { useEffect, useMemo, useState } from "react";
import { OpenCadApiClient } from "./api/client";
import { ChatPanel } from "./components/ChatPanel";
import { CadFileToolbar } from "./components/CadFileToolbar";
import { FeatureTreePanel } from "./components/FeatureTreePanel";
import { SketchEditor } from "./components/SketchEditor";
import { Viewport3D } from "./components/Viewport3D";
import { mockMeshes } from "./mock/mockData";
import { sketchFromNode } from "./sketchData";
import { createEmptyTree } from "./types";
import type { CadFileFormat, ChatOperationExecution, FeatureNodeView, FeatureTreeView, MeshPayload } from "./types";

const FALLBACK_MESH_Y_OFFSET_SCALE = 0.35;

function getLatestGeneratedNodeId(
  previousTree: FeatureTreeView,
  nextTree: FeatureTreeView,
  operations: ChatOperationExecution[],
): string | null {
  for (let index = operations.length - 1; index >= 0; index -= 1) {
    const result = operations[index].result;
    const featureId = typeof result.feature_id === "string" ? result.feature_id : null;
    if (featureId && nextTree.nodes[featureId]) {
      return featureId;
    }
  }

  const newNodeIds = Object.keys(nextTree.nodes).filter((nodeId) => !previousTree.nodes[nodeId]);
  for (let index = newNodeIds.length - 1; index >= 0; index -= 1) {
    const nodeId = newNodeIds[index];
    if (nextTree.nodes[nodeId]?.shape_id) {
      return nodeId;
    }
  }

  return newNodeIds.length > 0 ? newNodeIds[newNodeIds.length - 1] : null;
}

function createFallbackMesh(node: FeatureNodeView, index: number): MeshPayload {
  const template = mockMeshes[index % mockMeshes.length];
  const offset = (index + 1) * 8;

  return {
    shapeId: node.shape_id ?? node.id,
    name: node.name,
    vertices: Array.from(template.vertices, (value, vertexIndex) => {
      if (vertexIndex % 3 === 0) {
        return value + offset;
      }
      if (vertexIndex % 3 === 1) {
        return value + offset * FALLBACK_MESH_Y_OFFSET_SCALE;
      }
      return value;
    }),
    faces: Array.from(template.faces),
    normals: template.normals ? Array.from(template.normals) : undefined,
  };
}

export default function App(): JSX.Element {
  const api = useMemo(() => new OpenCadApiClient(), []);
  const [tree, setTree] = useState<FeatureTreeView>(createEmptyTree);
  const [meshes, setMeshes] = useState<MeshPayload[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string>(tree.root_id);

  const selectedShapeId = tree.nodes[selectedNodeId]?.shape_id ?? null;
  const selectedNode = tree.nodes[selectedNodeId] ?? null;
  const selectedSketch = useMemo(() => sketchFromNode(selectedNode), [selectedNode]);
  const loadedShapeIds = useMemo(() => new Set(meshes.map((mesh) => mesh.shapeId)), [meshes]);

  useEffect(() => {
    const missingShapeNodes = Object.values(tree.nodes).filter(
      (node) =>
        node.status === "built"
        && !node.suppressed
        && Boolean(node.shape_id)
        && !loadedShapeIds.has(node.shape_id as string),
    );

    if (missingShapeNodes.length === 0) {
      return;
    }

    let cancelled = false;

    void Promise.all(
      missingShapeNodes.map(async (node, index) => {
        try {
          return await api.getMesh(node.shape_id as string);
        } catch {
          return createFallbackMesh(node, index);
        }
      }),
    ).then((loadedMeshes) => {
      if (cancelled) {
        return;
      }

      setMeshes((current) => {
        const knownShapeIds = new Set(current.map((mesh) => mesh.shapeId));
        return [...current, ...loadedMeshes.filter((mesh) => !knownShapeIds.has(mesh.shapeId))];
      });
    });

    return () => {
      cancelled = true;
    };
  }, [api, loadedShapeIds, tree]);

  return (
    <div className="app-shell">
      <FeatureTreePanel
        tree={tree}
        selectedNodeId={selectedNodeId}
        onSelectNode={(nodeId) => setSelectedNodeId(nodeId)}
      />

      <main className="workspace">
        <CadFileToolbar
          canExport={Boolean(selectedShapeId)}
          onImport={async (file) => {
            const imported = await api.importCadFile(file);
            const nodeId = `import-${imported.shape_id}`;
            const importedNode: FeatureNodeView = {
              id: nodeId,
              name: imported.filename,
              operation: imported.format === "stl" ? "import_stl" : "import_step",
              parameters: { filename: imported.filename, format: imported.format },
              typed_parameters: {},
              parameter_bindings: [],
              sketch_id: null,
              parent_id: null,
              tool_refs: [],
              depends_on: [],
              shape_id: imported.shape_id,
              status: "built",
              suppressed: false,
            };
            setTree((current) => ({
              ...current,
              nodes: { ...current.nodes, [nodeId]: importedNode },
              revision: current.revision + 1,
            }));
            setSelectedNodeId(nodeId);
          }}
          onExport={async (format: CadFileFormat) => {
            if (!selectedShapeId) return;
            const baseName = (selectedNode?.name ?? "opencad-shape").replace(/\.(step|stp|stl)$/i, "");
            const filename = `${baseName}.${format}`;
            const blob = await api.exportCadFile(selectedShapeId, format, filename);
            const downloadUrl = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = downloadUrl;
            anchor.download = filename;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(downloadUrl);
          }}
        />
        <Viewport3D
          meshes={meshes}
          selectedShapeId={selectedShapeId}
          onSelectShape={(shapeId) => {
            const node = Object.values(tree.nodes).find((item) => item.shape_id === shapeId);
            if (node) {
              setSelectedNodeId(node.id);
            }
          }}
        />
        <SketchEditor
          key={selectedNodeId}
          active={selectedSketch !== null}
          name={selectedNode?.name ?? "Sketch"}
          sketch={selectedSketch}
          solveSketch={(payload) => api.solveSketch(payload)}
          onApply={async (updated) => {
            if (!selectedNode) {
              return;
            }
            const nextTree = await api.updateSketch(tree, selectedNode.id, updated);
            const liveShapeIds = new Set(
              Object.values(nextTree.nodes).map((node) => node.shape_id).filter(Boolean),
            );
            setMeshes((current) => current.filter((mesh) => liveShapeIds.has(mesh.shapeId)));
            setTree(nextTree);
          }}
        />
      </main>

      <ChatPanel
        onSend={async (request) => {
          const response = await api.sendChat({
            ...request,
            tree_state: tree,
          });
          const nextTree = response.new_tree_state;
          const liveShapeIds = new Set(
            Object.values(nextTree.nodes).map((n) => n.shape_id).filter(Boolean)
          );
          setMeshes((current) => current.filter((mesh) => liveShapeIds.has(mesh.shapeId)));
          setTree(nextTree);
          const latestNodeId = getLatestGeneratedNodeId(tree, nextTree, response.operations_executed);
          if (latestNodeId) {
            setSelectedNodeId(latestNodeId);
          }
          return {
            response: response.response,
            operations: response.operations_executed
          };
        }}
      />
    </div>
  );
}
