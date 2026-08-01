# Architecture

## Core / Backend Boundary

The core is a separate distribution from the backend, not just a separate
directory. OpenCAD is a uv workspace of three Python packages:

| Distribution | Location | Ships | Depends on |
|--------------|----------|-------|------------|
| `opencad` | `packages/opencad` | `opencad`, `opencad_kernel`, `opencad_solver`, `opencad_tree` | pydantic, numpy |
| `opencad-agent` | `packages/opencad-agent` | `opencad_agent` | `opencad`; `[llm]` adds LiteLLM |
| `opencad-backend` | `apps/backend` | `opencad_server` | `opencad`, `opencad-agent[llm]`, FastAPI, httpx, uvicorn |

The dependency arrow runs core ← agent ← backend and never reverses. `pip
install opencad` gets you a working geometry kernel, solver, feature tree,
fluent API, and CLI with no web framework anywhere in the environment.

Two mechanisms keep it that way:

1. `apps/backend/tests/test_core_boundary.py` parses every non-test module in
   the core packages and fails on any import of `fastapi`, `starlette`,
   `httpx`, `uvicorn`, `sse_starlette`, `dotenv`, or `opencad_server`.
2. CI runs a job per package with `uv sync --package <name>`, so each test
   suite executes with only that package's own dependencies installed. A core
   module that reaches for the backend fails to import, not just to lint.

### Backend contents (`apps/backend/src/opencad_server`)

- `app.py` — aggregate app; mounts every router under `/kernel`, `/agent`, `/solver`, `/tree`
- `kernel_router.py`, `solver_router.py`, `tree_router.py`, `agent_router.py`
  — one router per service, each also exposing `create_app()` and a module-level
  `app` for standalone deployment
- `api_app.py` — shared FastAPI factory with production CORS/docs defaults
- `http_kernel_client.py` — the only outbound HTTP client to the kernel

### Kernel access contract

Core code that needs the kernel depends on the `KernelClient` protocol in
`opencad_kernel/client.py`, never on a transport:

```python
class KernelClient(Protocol):
    def call_operation(self, operation: str, params: dict) -> dict: ...
    def get_topology(self, shape_id: str) -> dict: ...
    def get_mesh(self, shape_id: str, deflection: float = 0.1) -> dict: ...
```

Two implementations exist:

- `opencad_kernel.client.LocalKernelClient` — in-process, backed by an
  `OperationRegistry`. Used by `RuntimeContext`, the CLI, and tests.
- `opencad_server.http_kernel_client.HttpKernelClient` — remote, backed by httpx.
  Selected in `agent_router.py` and `tree_router.py` when
  `OPENCAD_AGENT_LIVE_KERNEL` or `OPENCAD_TREE_LIVE_KERNEL` is true.

`RuntimeContext`, `OpenCadAgentService`, and `ToolRuntime` all accept a
`kernel_client`; the choice of transport is made once, at the composition root.

### Agent ← core direction

The core knows nothing about the agent. Driving a `RuntimeContext` with the LLM
lives in the agent package as `opencad_agent.run_chat(context, message)`, which
calls back into the core's public surface (`context.kernel_client`,
`context.adopt_tree`). There is no lazy `import opencad_agent` inside `opencad`.

## Geometry Backend Boundary

- `opencad_kernel.operations.handlers.OpenCadKernel` is the stable coordinator used by the registry and public APIs.
- Geometry is implemented behind `KernelBackend`; the coordinator contains no geometry algorithms.
- `opencad_kernel.core.occt_backend.OcctBackend` owns production B-rep construction, topology, file I/O, and tessellation.
- `opencad_kernel.core.analytic_backend.AnalyticBackend` owns the metadata-only approximation used by lightweight and isolated tests.
- Assembly mates and the shared topology selector stay in the coordinator because they are application-level behavior rather than geometry-engine behavior.
- Every operation-log entry records the concrete backend class that executed it, allowing snapshots and diagnostics to distinguish analytic results from OCCT results.
- Face-by-face mesh streaming is tracked separately through the optional `StreamingMeshBackend` capability.

## 4 – Viewport Application (`opencad_viewport`)

### Frontend Components

- `Viewport3D`
  - Three.js scene (React Three Fiber)
  - Orbit/pan/zoom controls
  - Flat-shaded mesh render + edge highlights
  - Selection highlighting in blue
  - Grid aligned at `Z=0` and gizmo axis indicator
- `FeatureTreePanel`
  - Dependency tree display from `FeatureTree`
  - Expand/collapse parent nodes
  - Operation badges and status markers
  - Node selection callback into viewport
- `SketchEditor`
  - SVG overlay mode
  - Constraint icons rendered near entities
  - Calls solver API (or mock solver) whenever constraints change
- `ChatPanel`
  - Prompt input + send flow
  - Streaming assistant response rendering
  - Operation execution list with per-step status

### Data Contracts

- Mesh contract:
  - `GET /shape/{id}/mesh -> { vertices, faces, normals }`
- Tree contract:
  - `GET /tree -> FeatureTree`
- Feature updates:
  - `POST /feature`
  - `PATCH /feature/{id}`
  - `POST /trees/{tree_id}/nodes/{node_id}/typed-parameters`
  - `POST /trees/{tree_id}/nodes/{node_id}/suppress`
  - `POST /trees/{tree_id}/branches`
  - `POST /trees/{tree_id}/branches/{branch_name}/switch`
  - `POST /trees/{tree_id}/solver/{sketch_id}`

### Mock-First Development

The viewport client (`src/api/client.ts`) uses live geometry/solver flows by default; mock mode is opt-in via `VITE_USE_MOCK=true`.
Chat uses the live agent service by default, with an opt-in mocked chat path via `VITE_USE_CHAT_MOCK=true`.

### Storybook Coverage

- `Viewport3D.stories.tsx`
- `FeatureTreePanel.stories.tsx`
- `SketchEditor.stories.tsx`
- `ChatPanel.stories.tsx`

## 5 – Agent Service (`opencad_agent`)

### Service Responsibilities

- Accept natural language feature requests
- Build a full operation sequence before execution
- Execute tool calls against an in-memory feature-tree runtime
- Return:
  - Human-readable response
  - Structured `operations_executed`
  - Updated `FeatureTree`

### API

- `GET /healthz`
- `POST /chat`
  - Input:
    - `message: str`
    - `tree_state: FeatureTree`
    - `conversation_history: []`
    - `llm_provider: str | null` (optional, for LiteLLM-backed code generation)
    - `llm_model: str | null` (optional, for LiteLLM-backed code generation)
  - Output:
    - `response: str`
    - `generated_code: str | null`
    - `operations_executed: []`
    - `new_tree_state: FeatureTree`

### Internal Modules

- `prompting.py`
  - Builds required system prompt sections:
    - current tree state
    - available operation schemas
    - naming and validation instructions
    - example-script references for code generation
- `tools.py`
  - Tool runtime for:
    - `add_sketch`
    - `extrude`
    - `boolean_cut`
    - `fillet_edges`
    - `add_cylinder`
    - `get_tree_state`
    - `get_shape_info`
- `service.py`
  - Always generates OpenCAD code through LiteLLM
  - Validates, repairs once when needed, executes, and returns the updated tree

## Cross-Service Integration

- 4 (`ChatPanel`) calls 5 (`/chat`)
- 5 outputs updated `FeatureTree`
- 4 `FeatureTreePanel` renders updated nodes/status
- 4 `SketchEditor` calls 2 solver endpoint
- 2 solver results can feed 3 feature-tree parameter bindings (`source=solver`)
- 4 mesh loading contract aligns to 1/3 shape identity model

## 7 - Parametric Feature DAG (Incremental)

- Feature nodes support typed inputs (`typed_parameters`) and explicit binding metadata (`parameter_bindings`).
- Rebuild is incremental: only `pending`, `stale`, or `failed` nodes with all parents in `built` state are executed.
- Suppression is first-class (`suppressed=true`): suppressed nodes produce no shape and stale descendants until re-enabled.
- Branching is snapshot-based (`branch_snapshots` + `active_branch`) for fast variant exploration and deterministic replay.
- Full history export is JSON-native through tree serialization, including branch snapshots and solver cache values.

## 8 - Single-Process Headless Runtime (`opencad`)

OpenCAD now supports a headless mode where kernel, tree, and fluent API calls execute in one Python process.

### Runtime Composition

- `opencad.runtime.RuntimeContext`
  - Owns `OpenCadKernel`, `OperationRegistry`, and in-memory `FeatureTree`
  - Executes operations without inter-service HTTP
  - Tracks latest feature and shape IDs for fluent chaining
  - Supports tree serialization/deserialization and in-process rebuild
  - Exposes `kernel_client` and `adopt_tree()` so `opencad_agent.run_chat()` can drive it in-process

### Fluent API

- `opencad.part.Part`
  - Kernel-backed v1 methods for primitives, booleans, extrude, edge/face ops, patterns, and export
- `opencad.sketch.Sketch`
  - Fluent segment builder (`line`, `rect`, `circle`) that materializes via `create_sketch`
- Public import surface:
  - `from opencad import Part, Sketch`

### DAG as a Byproduct

Every fluent call appends a `FeatureNode` to the active tree branch.

- Operation execution and DAG writes are coupled in `RuntimeContext.execute_operation`
- Dependencies are recorded as feature-node IDs (not only shape IDs)
- Resulting tree can be persisted and rebuilt with `FeatureTreeService`

### In-Process Agent Geometry Path

When `ToolRuntime` has an injected `KernelClient` (single-process mode), it now:

- Converts supported sketch entities to `create_sketch` segments
- Calls kernel `extrude` against the created sketch shape when available
- Falls back to synthetic/legacy approximations only when conversion is not possible

Current planner output now prefers explicit sketch entities (`line`, `circle`) over point-only payloads,
which improves deterministic translation to kernel sketch segments in headless mode.

Planner sketch payloads may also include `profile_order` (entity ID sequence) to guarantee
deterministic loop ordering independent of dictionary iteration order.

The fluent `opencad.Sketch` path now writes the same `entities` + `profile_order` metadata
into sketch feature-node parameters, aligning script-authored sketches with agent-authored
sketch ordering semantics.

### CLI for CI/CD

- `opencad build model.json --output model.built.json`
  - Loads a tree JSON model and rebuilds it in-process
- `opencad run model.py --export output.step --tree-output output-tree.json`
  - Executes fluent scripts in-process and optionally exports STEP + tree JSON

This path is intended for script-first workflows where users want Build123d-like ergonomics while retaining recoverable, editable feature DAG state.

## 6 — Constraint Solving Architecture

### Pluggable Solver Backend

The solver service (`opencad_solver`) uses a backend abstraction (`SolverBackend` ABC
in `opencad_solver/backend.py`) to decouple constraint-solving logic from the API layer.

- **PythonSolverBackend** (default) — NumPy/SciPy Gauss-Newton with numerical Jacobian.
- **SolveSpaceBackend** — delegates to SolveSpace via `python-solvespace` bindings.
  Falls back gracefully when the package is not installed.
- Backend selection: `OPENCAD_SOLVER_BACKEND=solvespace|python|auto` (auto prefers SolveSpace).

### Constraint-Graph Introspection

`POST /sketch/diagnose` returns `ConstraintDiagnostics` with:

| Field | Description |
|-------|-------------|
| `dof` | Remaining degrees of freedom |
| `status` | `SOLVED`, `UNDERCONSTRAINED`, `OVERCONSTRAINED` |
| `jacobian` | `JacobianInfo` — shape, rank, sparse nonzero `(row, col)` pairs |
| `variables` | `VariableInfo[]` — maps solver variable index → entity ID + parameter name |
| `constraints` | `ConstraintInfo[]` — maps constraint → row span + residual norm |
| `over_constrained_ids` | Constraint IDs with high residual (conflicting) |
| `under_constrained_variables` | Variable indices with near-zero Jacobian column norm |

This is the primary API for AI agents reasoning about constraint state.

### 3-D Assembly Mates (Phase 1)

Assembly mates are first-class kernel operations registered in the operation registry:

- `create_assembly_mate` — validates entity references, creates mate in `MateStore`.
- `delete_assembly_mate` — removes a mate by ID.
- `list_assembly_mates` — lists all mates, optionally filtered by entity involvement.

Supported mate types: `coincident`, `concentric`, `distance`, `angle`, `parallel`, `perpendicular`.

Mates are modeled as feature nodes in the tree with `is_assembly_mate=True` and bidirectional
dependencies on the constrained shapes. When either shape rebuilds, the mate node goes stale.

### Phase 2 — Part-Level 3-D Constraints

Requires topology reference stability. See [TOPOLOGY.md](TOPOLOGY.md) for:
- Problem statement and concrete failure walkthrough
- Prior-art analysis (FreeCAD TNaming, Build123d hash tracking, Fusion 360, STEP)
- Community proposal template and acceptance criteria

## Validation Coverage

- `opencad_agent/tests/test_agent.py` verifies:
  - system prompt completeness
  - fixed low-temperature, non-reasoning LLM settings
  - generated-code policy and execution
  - API round-trip and health endpoint
