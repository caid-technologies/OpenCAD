# OpenCAD

A modular CAD system for parametric, programmable, and AI-assisted design

## Components

- `opencad_kernel` — geometry kernel and typed operation registry
- `opencad_solver` — 2D sketch constraint solving (SolveSpace + Python fallback)
- `opencad_tree` — parametric feature-tree DAG (CRUD + rebuild + stale propagation)
- `opencad_agent` — AI agent that plans and executes operations
- `opencad_viewport` — React + Three.js viewport UI (mock mode by default)

## Layout

```text
opencad_kernel/      # 1 – Geometry Kernel
opencad_solver/      # 2 – Constraint Solver
opencad_tree/        # 3 – Feature Tree
opencad_viewport/    # 4 – 3D Viewport (frontend)
opencad_agent/       # 5 – AI Chat Agent
scripts/             # Backend smoke tests
```

## Quickstart

**Prereqs:** Python 3.11+ and Node.js 18+

### 1. Install

For a packaged install (for example from a wheel or a PyPI release), use:

```bash
uv pip install opencad
```

For local development from this repository:

```bash
uv sync --extra test --extra server
cp .env.example .env
```

Install optional integrations as needed, for example:

```bash
uv sync --extra occt
uv sync --extra llm
uv sync --extra full
```

### 2. Start backend services

Each service runs on its own port:

```bash
cd backend
uv run --no-sync python -m uvicorn api:app --reload --port 8000
```

### Run the dev script

To start the backend and frontend together from the repository root:

```bash
cd opencad_viewport
pnpm install
cd ..
./scripts/run_dev.sh
```

This starts:

- backend: `http://127.0.0.1:8000`
- frontend: `http://127.0.0.1:5173`

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
cd opencad_viewport
pnpm install
pnpm dev                                 # → http://localhost:5173
```

The viewport uses **mock geometry/solver data** by default (no backend required for those flows).
Chat targets the live agent service by default; set `VITE_USE_CHAT_MOCK=true` if you explicitly want mocked chat output.
Set `VITE_USE_MOCK=false` to connect the rest of the viewport to the live services above.

### 5. Run with Docker

Build the backend image from the repository root so Docker can see the Python
project metadata and backend package files:

```bash
docker build -f backend/Dockerfile -t opencad-backend .
```

Build the frontend image from the viewport directory:

```bash
docker build -f opencad_viewport/Dockerfile -t opencad-frontend opencad_viewport
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
  -f opencad_viewport/Dockerfile \
  -t opencad-frontend \
  --build-arg VITE_BASE_URL=http://localhost:8000 \
  --build-arg VITE_USE_MOCK=false \
  --build-arg VITE_USE_CHAT_MOCK=false \
  opencad_viewport
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

```bash
uv run --no-sync python -m pytest
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
```

## Examples

The [`examples/`](examples/README.md) directory contains end-to-end scripts for common
device-development workflows:

- `hardware_mounting_bracket.py` — bracket with fastener and cable pass-through holes
- `hardware_pcb_carrier.py` — PCB carrier plate with mounting holes and clearance slot
- `software_hmi_panel.py` — front panel for an operator interface with button and encoder cutouts
- `firmware_programmer_fixture.py` — pogo-pin fixture plate for programming/debug access
- `full_device_cable_grommet.py` — concentric cable grommet built from primitive booleans
- `examples/agents/generate_mounting_bracket_code.py` — agent code-generation usage example

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

For a runnable script example, see [`examples/agents/README.md`](examples/agents/README.md).

## Documentation

- [CHANGELOG.md](CHANGELOG.md) - release notes
- [CONTRIBUTING.md](CONTRIBUTING.md) - development and contract workflow
- [docs/CAID_ARTIFACT_CONTRACT.md](docs/CAID_ARTIFACT_CONTRACT.md) - artifact and patch semantics
- [docs/RECONSTRUCTION_AND_UPGRADE_PLAN.md](docs/RECONSTRUCTION_AND_UPGRADE_PLAN.md) - local reconstruction status and CAID upgrade plan

- [PRODUCTION.md](PRODUCTION.md) — deployment, routes, and verification
- [ARCHITECTURE.md](ARCHITECTURE.md) — component design and API contracts
- [TOPOLOGY.md](TOPOLOGY.md) — topology reference stability (open research question)
- [SECURITY.md](SECURITY.md) — vulnerability reporting and hardening baseline
