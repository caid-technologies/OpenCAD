# OpenCAD

A modular CAD system for parametric, programmable, and AI-assisted design

## Install for Claude or Codex

Install the OpenCAD skill with one command:

```bash
npx skills add caid-technologies/OpenCAD
```

Then ask the agent normally:

```text
Create a 72 mm round spray bottle and give me STEP and STL files.
```

The agent writes the parametric source, builds real OCCT geometry, validates
the artifacts, and returns clickable file paths. No manual Python or CLI work
is required from the user. The repository also ships provider-native manifests
under `.codex-plugin/` and `.claude-plugin/`.

## Components

- `opencad.kernel` — geometry kernel and typed operation registry
- `opencad.solver` — 2D sketch constraint solving (SolveSpace + Python fallback)
- `opencad.tree` — parametric feature-tree DAG (CRUD + rebuild + stale propagation)
- `opencad_agent` — AI agent that plans and executes operations
- `opencad_server` — FastAPI transport mounting all of the above
- `opencad-viewport` — publishable React + Three.js component library (npm)

## Layout

This is a uv workspace of three Python distributions and a pnpm workspace
holding one npm package, all independently installable. The core carries no
web framework: the dependency arrow runs core ← agent ← backend and never the
other way. Applications under `apps/` are never published; they consume the
libraries under `packages/`.

```text
packages/
├── opencad/             # dist: opencad — kernel, solver, tree, fluent API, CLI
│   ├── src/             #   pydantic + numpy only. No FastAPI, no httpx.
│   └── tests/
├── opencad-agent/       # dist: opencad-agent — LLM modelling on the core
│   ├── src/             #   depends on opencad; [llm] extra adds LiteLLM
│   └── tests/
└── opencad-viewport/    # npm: opencad-viewport — React component library
    └── src/             #   react/three are peer deps, never bundled
apps/
├── backend/             # dist: opencad-backend — the only FastAPI consumer
│   ├── src/             #   opencad_server: routers, app factory, HTTP client
│   └── tests/
└── opencad_viewport/    # reference app hosting the components (not published)
scripts/                 # Development and smoke-test scripts
```

Each package installs and tests on its own; CI runs a job per package with
only that package's dependencies present, so a core module that reaches for
the backend fails the build.

## Quickstart

**Prereqs:** Python 3.11+ and Node.js 18+

### 1. Install

For a packaged install, pick the layer you need — each is independent:

```bash
uv pip install "opencad[occt]"        # core only: kernel, solver, tree, fluent API
uv pip install "opencad-agent[llm]"   # + natural-language modelling
uv pip install opencad-backend        # + the FastAPI HTTP service
```

For local development from this repository:

```bash
uv sync --all-packages --all-extras --group test
cp .env.example .env
```

To work on one package in isolation, sync only its dependencies:

```bash
uv sync --package opencad --group test          # core alone, no web stack
uv sync --package opencad-agent --group test    # core + agent
uv sync --package opencad-backend --group test  # everything
```

### 2. Start backend services

```bash
uv run --package opencad-backend --extra occt \
  python -m uvicorn opencad_server.app:app --reload --port 8000
```

`opencad_server.app` mounts every service router under one process. To run a
single service standalone, point uvicorn at its router module instead — for
example `opencad_server.kernel_router:app` or `opencad_server.solver_router:app`.

### Run the dev script

To start the backend and frontend together from the repository root:

```bash
cd apps/opencad_viewport
pnpm install
cd ../..
./scripts/run_dev.sh
```

This starts:

- backend: `http://127.0.0.1:8000`
- frontend: `http://127.0.0.1:5173`

The launcher syncs the backend server, LLM, and OCCT dependencies before startup.

Press `Ctrl+C` to stop both services.

Optional environment overrides:

```bash
BACKEND_HOST=0.0.0.0 BACKEND_PORT=8000 FRONTEND_HOST=0.0.0.0 FRONTEND_PORT=5173 ./scripts/run_dev.sh
```

### 3. Check health

```bash
curl -s http://127.0.0.1:8000/kernel/healthz   # → {"status":"ok"}
curl -s http://127.0.0.1:8000/agent/healthz
curl -s http://127.0.0.1:8000/solver/healthz
curl -s http://127.0.0.1:8000/tree/healthz
```

### 4. Start the frontend

```bash
pnpm install                             # from the repository root
pnpm --filter opencad-viewport build     # build the component library first
pnpm --filter opencad-viewport-app dev   # → http://localhost:5173
```

The viewport uses **mock geometry/solver data** by default (no backend required for those flows).
Chat targets the live agent service by default; set `VITE_USE_CHAT_MOCK=true` if you explicitly want mocked chat output.
Set `VITE_USE_MOCK=false` to connect the rest of the viewport to the live services above.

### 5. Run with Docker

Build the backend image from the repository root so Docker can see the Python
project metadata and backend package files:

```bash
docker build -f apps/backend/Dockerfile -t opencad-backend .
```

Build the frontend image from the repository root too — the app depends on the
`opencad-viewport` workspace library:

```bash
docker build -f apps/opencad_viewport/Dockerfile -t opencad-frontend .
```

Run the backend API on port `8000`:

```bash
docker run --rm -p 8000:8000 opencad-backend
```

Run the frontend on port `5173`:

```bash
docker run --rm -p 5173:80 opencad-frontend
```

By default, the frontend image is built with `VITE_BASE_URL=http://localhost:8000`
and live API calls enabled. To point the frontend at another API URL or enable
mock mode, pass build args:

```bash
docker build \
  -f apps/opencad_viewport/Dockerfile \
  -t opencad-frontend \
  --build-arg VITE_BASE_URL=http://localhost:8000 \
  --build-arg VITE_USE_MOCK=false \
  --build-arg VITE_USE_CHAT_MOCK=false \
  .
```

## Configuration

Runtime defaults are documented in `.env.example`.

- `OPENCAD_ENABLE_DOCS=true|false` toggles OpenAPI/docs route exposure.
- `OPENCAD_CORS_ALLOW_ORIGINS` sets a comma-separated browser origin allowlist.
- `OPENCAD_KERNEL_BACKEND=analytic|occt` selects the kernel backend.
- `OPENCAD_SOLVER_BACKEND=auto|solvespace|python` selects the solver backend.

For production, disable docs and set a strict CORS origin list.

## Security

Use TLS + authentication at your reverse proxy/API gateway.
Do not commit `.env` files, tokens, or private datasets.
See `SECURITY.md` for coordinated vulnerability reporting.

## Testing

Run the whole workspace:

```bash
uv sync --all-packages --group test
uv run --no-sync python -m pytest
```

Or test one package with only its own dependencies installed — this is what CI
does, and it is what keeps the core independent of the backend:

```bash
uv sync --package opencad --group test
cd packages/opencad && uv run --no-sync --package opencad --project ../.. python -m pytest
```

## Headless Scripting

OpenCAD now includes a first-class in-process API for scripting workflows with automatic feature-tree logging.

```python
from opencad import Part, Sketch

part = Part()
sketch = Sketch().rect(10, 20).circle(3, subtract=True)
part.extrude(sketch, depth=5).fillet(edges="top", radius=0.5)
part.export("output.step")
```

Every fluent call appends a built `FeatureNode` to the in-memory DAG, so headless runs are recoverable.
Fluent sketches also persist `entities` + `profile_order` metadata in the sketch node, matching agent-path ordering semantics for deterministic profile reconstruction.

## CAID Design Artifact

OpenCAD can export a versioned JSON artifact for SimCorrect. The artifact carries the feature tree, named parameters, and simulation tags; SimCorrect returns structured parameter patches against those names.

```python
from opencad import Part, Sketch

part = Part(name="forearm").extrude(Sketch().rect(30, 4), depth=4)
part.export_design_artifact(
    "caid-design.json",
    artifact_id="forearm-demo",
    parameters={"forearm_length": {"value": 0.30, "unit": "m", "role": "geometry"}},
    simulation_tags=[
        {"name": "right_forearm", "kind": "body", "target": "r_forearm"},
        {"name": "forearm_length", "kind": "parameter", "target": "link2_length"},
    ],
)
```

## CLI

```bash
opencad build model.json --output model.built.json
opencad run model.py --export output.step --tree-output output-tree.json
opencad run model.py --export output.stl --tree-output output-tree.json
```

STEP and STL export use the native OCCT backend. Install it with
`uv sync --extra occt`; the CLI's default `--backend auto` mode selects it
automatically whenever `--export` is requested. The analytic backend can be
selected explicitly for tree-only validation with `--backend analytic`, but it
does not produce user-deliverable CAD files.

## Claude and Codex skill

The installable `create-cad-files` skill lives under `skills/create-cad-files`.
Small repository adapters under `.agents/skills` and `.claude/skills` make the
same workflow available automatically while developing OpenCAD. It turns a
dimensional request into an OpenCAD Python model, then atomically exports and
validates STEP, STP, or STL.

## Examples

The [`examples/`](examples/README.md) directory contains end-to-end scripts for common
device-development workflows:

- `hardware_mounting_bracket.py` — bracket with fastener and cable pass-through holes
- `hardware_pcb_carrier.py` — PCB carrier plate with mounting holes and clearance slot
- `software_hmi_panel.py` — front panel for an operator interface with button and encoder cutouts
- `firmware_programmer_fixture.py` — pogo-pin fixture plate for programming/debug access
- `full_device_cable_grommet.py` — concentric cable grommet built from primitive booleans
- `round_spray_bottle.py` — circular reservoir with an integrated trigger and nozzle

Run an example from the repository root with:

```bash
python -m opencad.cli run examples/hardware_mounting_bracket.py \
  --export bracket.step \
  --tree-output bracket-tree.json
```

The agent service generates and executes OpenCAD Python through LiteLLM for every `/chat`
request. Provider and model can be supplied as `llm_provider` and `llm_model`, or configured
with `OPENCAD_LLM_PROVIDER` and `OPENCAD_LLM_MODEL`. Responses include `generated_code`,
executed operations, and the updated feature tree.

## Documentation

- [CHANGELOG.md](CHANGELOG.md) - release notes
- [CONTRIBUTING.md](CONTRIBUTING.md) - development and contract workflow
- [docs/CAID_ARTIFACT_CONTRACT.md](docs/CAID_ARTIFACT_CONTRACT.md) - artifact and patch semantics
- [docs/RECONSTRUCTION_AND_UPGRADE_PLAN.md](docs/RECONSTRUCTION_AND_UPGRADE_PLAN.md) - local reconstruction status and CAID upgrade plan

- [PRODUCTION.md](PRODUCTION.md) — deployment, routes, and verification
- [ARCHITECTURE.md](ARCHITECTURE.md) — component design and API contracts
- [TOPOLOGY.md](TOPOLOGY.md) — topology reference stability (open research question)
- [SECURITY.md](SECURITY.md) — vulnerability reporting and hardening baseline
