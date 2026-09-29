import { useEffect, useMemo, useState } from "react";
import {
  CadFileToolbar,
  ChatPanel,
  FeatureTreePanel,
  OpenCadApiClient,
  SketchEditor,
  ScenePlayer,
  robotPickPlaceExample,
  Viewport3D,
  createEmptyTree,
  getHighlightedViewportShapeIds,
  getViewportShapeIds,
  sketchFromNode,
} from "opencad-viewport";
import type {
  CadFileFormat,
  ChatOperationExecution,
  FeatureNodeView,
  FeatureTreeView,
  MeshPayload,
} from "opencad-viewport";

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

export default function App(): JSX.Element {
  const [showScene, setShowScene] = useState(false);
  const api = useMemo(() => new OpenCadApiClient(), []);
  const [tree, setTree] = useState<FeatureTreeView>(createEmptyTree);
  const [meshErrors, setMeshErrors] = useState<Record<string, string>>({});
  const [meshRetry, setMeshRetry] = useState(0);
  const [meshes, setMeshes] = useState<MeshPayload[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string>(tree.root_id);

  const selectedShapeId = tree.nodes[selectedNodeId]?.shape_id ?? null;
  const selectedNode = tree.nodes[selectedNodeId] ?? null;
  const selectedSketch = useMemo(() => sketchFromNode(selectedNode), [selectedNode]);
  const viewportShapeIds = useMemo(() => getViewportShapeIds(tree), [tree]);
  const highlightedShapeIds = useMemo(
    () => getHighlightedViewportShapeIds(tree, selectedNodeId, viewportShapeIds),
    [selectedNodeId, tree, viewportShapeIds],
  );
  const loadedShapeIds = useMemo(() => new Set(meshes.map((mesh) => mesh.shapeId)), [meshes]);
  const viewportMeshes = useMemo(
    () => meshes.filter((mesh) => viewportShapeIds.has(mesh.shapeId)),
    [meshes, viewportShapeIds],
  );

  useEffect(() => {
    const missingShapeNodes = Object.values(tree.nodes).filter(
      (node) =>
        node.status === "built"
        && !node.suppressed
        && Boolean(node.shape_id)
        && viewportShapeIds.has(node.shape_id as string)
        && !loadedShapeIds.has(node.shape_id as string)
        && !meshErrors[node.shape_id as string],
    );

    if (missingShapeNodes.length === 0) {
      return;
    }

    let cancelled = false;

    void Promise.all(
      missingShapeNodes.map(async (node) => {
        try {
          return { mesh: await api.getMesh(node.shape_id as string), node };
        } catch {
          return { mesh: null, node };
        }
      }),
    ).then((loadedMeshes) => {
      if (cancelled) {
        return;
      }

      setMeshErrors((current) => ({ ...current, ...Object.fromEntries(
        loadedMeshes.filter(({ mesh }) => mesh === null).map(({ node }) => [
          node.shape_id as string,
          `Could not load geometry for ${node.name}. Retry, or regenerate the shape if the backend restarted.`,
        ]),
      ) }));
      const successfulMeshes = loadedMeshes.flatMap(({ mesh }) => mesh ? [mesh] : []);
      if (successfulMeshes.length === 0) return;
      setMeshes((current) => {
        const knownShapeIds = new Set(current.map((mesh) => mesh.shapeId));
        return [...current, ...successfulMeshes.filter((mesh) => !knownShapeIds.has(mesh.shapeId))];
      });
    });

    return () => {
      cancelled = true;
    };
  }, [api, loadedShapeIds, tree, viewportShapeIds, meshErrors, meshRetry]);

  if (showScene) {
    return <main className="scene-demo">
      <header>
        <button type="button" className="scene-demo-toggle" onClick={() => setShowScene(false)}>Back to CAD</button>
        <p>Independent scene roots: Robot arm · Box · Destination table</p>
      </header>
      <ScenePlayer document={robotPickPlaceExample.document} meshes={robotPickPlaceExample.meshes}
        onSave={(document) => {
          const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2)], { type: "application/json" }));
          const anchor = window.document.createElement("a");
          anchor.href = url;
          anchor.download = "robot-pick-place.scene.json";
          window.document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
          URL.revokeObjectURL(url);
        }} />
    </main>;
  }

  return (
    <div className="app-shell">
      <FeatureTreePanel
        tree={tree}
        selectedNodeId={selectedNodeId}
        onSelectNode={(nodeId) => setSelectedNodeId(nodeId)}
      />

      <main className="workspace">
        <button type="button" className="scene-demo-toggle" onClick={() => setShowScene(true)}>Robot pick-and-place demo</button>
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
        {Object.entries(meshErrors).filter(([id]) => viewportShapeIds.has(id)).length > 0 && (
          <div role="alert">
            {Object.entries(meshErrors).filter(([id]) => viewportShapeIds.has(id)).map(([id, message]) => (
              <p key={id}>{message}</p>
            ))}
            <button type="button" onClick={() => { setMeshErrors({}); setMeshRetry((value) => value + 1); }}>
              Retry loading geometry
            </button>
          </div>
        )}
        <Viewport3D
          meshes={viewportMeshes}
          selectedShapeId={selectedShapeId}
          highlightedShapeIds={highlightedShapeIds}
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
