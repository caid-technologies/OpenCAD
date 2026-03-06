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

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[full]"
cp .env.example .env
```

### 2. Start backend services

Each service runs on its own port:

```bash
python -m uvicorn opencad_kernel.api:app --reload --port 8000   # 1 – Kernel
python -m uvicorn opencad_solver.api:app --reload --port 8001   # 2 – Solver
python -m uvicorn opencad_tree.api:app   --reload --port 8002   # 3 – Tree
python -m uvicorn opencad_agent.api:app  --reload --port 8003   # 5 – Agent
```

### 3. Check health

```bash
curl -s http://127.0.0.1:8000/healthz   # → {"status":"ok"}
curl -s http://127.0.0.1:8001/healthz
curl -s http://127.0.0.1:8002/healthz
curl -s http://127.0.0.1:8003/healthz
```

### 4. Start the frontend

```bash
cd opencad_viewport
npm install
npm run dev                              # → http://localhost:5173
```

The viewport runs in **mock mode** by default (no backend required).
Set `VITE_USE_MOCK=false` to connect to the live services above.

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
pytest
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

## CLI

```bash
opencad build model.json --output model.built.json
opencad run model.py --export output.step --tree-output output-tree.json
```

## Documentation

- [PRODUCTION.md](PRODUCTION.md) — deployment, routes, and verification
- [ARCHITECTURE.md](ARCHITECTURE.md) — component design and API contracts
- [TOPOLOGY.md](TOPOLOGY.md) — topology reference stability (open research question)
- [SECURITY.md](SECURITY.md) — vulnerability reporting and hardening baseline
