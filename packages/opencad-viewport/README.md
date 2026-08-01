# opencad-viewport

React + Three.js components for building [OpenCAD](https://github.com/caid-technologies/OpenCAD)
front-ends: a 3D viewport, a parametric feature tree, a constraint sketch
editor, a chat panel, and a typed API client.

## Install

```bash
npm install opencad-viewport react react-dom three @react-three/fiber @react-three/drei
```

React, Three.js, and the react-three packages are **peer dependencies**. They
are singleton-sensitive — two copies of `three` break `instanceof` checks and
two copies of React cause invalid-hook-call errors — so this package never
bundles them.

## Use

```tsx
import {
  OpenCadApiClient,
  Viewport3D,
  FeatureTreePanel,
  createEmptyTree,
} from "opencad-viewport";
import "opencad-viewport/styles.css"; // opt-in

const client = new OpenCadApiClient();

export function App() {
  const [tree, setTree] = useState(createEmptyTree());
  const [meshes, setMeshes] = useState([]);
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <>
      <FeatureTreePanel tree={tree} selectedNodeId={selected} onSelectNode={setSelected} />
      <Viewport3D meshes={meshes} selectedShapeId={selected} onSelectShape={setSelected} apiClient={client} />
    </>
  );
}
```

The stylesheet is not imported by the entry point, so components are unstyled
until you import it. Skip it if you are supplying your own CSS for the
documented class names.

## Exports

| Component | Purpose |
|-----------|---------|
| `Viewport3D` | Three.js scene with orbit controls, flat-shaded meshes, edge highlights, selection |
| `FeatureTreePanel` | Feature DAG with expand/collapse, operation badges, status markers |
| `SketchEditor` | SVG constraint-sketch overlay that calls the solver on change |
| `ChatPanel` | Prompt input with streaming response and per-operation status |
| `CadFileToolbar` | STEP/STP/STL import and export controls |

| Helper | Purpose |
|--------|---------|
| `OpenCadApiClient` | Typed client for the kernel, solver, tree, and agent endpoints |
| `projectFeatureTree` | Flatten a feature tree into renderable rows |
| `getViewportShapeIds`, `getHighlightedViewportShapeIds` | Resolve which shapes are visible or highlighted |
| `getMeshMaterialGroups` | Split a mesh into material groups for face-level highlighting |
| `sketchFromNode` | Extract a sketch payload from a feature node |
| `mockMeshes`, `mockFeatureTree`, `mockSketch`, `mockChat`, `mockSolveSketch` | Fixtures for tests, stories, and offline development |

All view models (`FeatureTreeView`, `MeshPayload`, `SketchPayload`, …) are
exported as types.

## Backend

The components are transport-agnostic — they take data through props. The
included `OpenCadApiClient` targets an `opencad-backend` instance and defaults
to `http://127.0.0.1:8000`:

```ts
new OpenCadApiClient(agentUrl, baseUrl, useMock, useChatMock);
```

## Development

This package lives in the OpenCAD monorepo.

```bash
pnpm install          # from the repository root
pnpm --filter opencad-viewport build
pnpm --filter opencad-viewport test
```

`apps/opencad_viewport` is a reference application that consumes this package
through the workspace.

## License

Apache-2.0
