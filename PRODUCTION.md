# OpenCAD Production Notes

This document focuses on deploy shape and externally relevant runtime behavior.
Internal implementation details belong in architecture docs or source comments.

## Services

- 1 — `opencad_kernel.api` (default port `8000`)
  - `GET /healthz`
  - `GET /operations`
  - `GET /operations/{name}/schema`
  - `POST /operations/{name}`
  - Operations include: `create_assembly_mate`, `delete_assembly_mate`, `list_assembly_mates`
- 2 — `opencad_solver.api` (default port `8001`)
  - `GET /healthz`
  - `GET /backend` — active solver backend and capabilities
  - `POST /sketch/solve`
  - `POST /sketch/check`
  - `POST /sketch/diagnose` — constraint-graph introspection (DOF, Jacobian, mappings)
  - Backend selection: `OPENCAD_SOLVER_BACKEND=solvespace|python|auto`
- 3 — `opencad_tree.api` (default port `8002`)
  - `GET /healthz`
  - tree CRUD + rebuild + serialize/deserialize
  - Assembly mate nodes: `is_assembly_mate=true` with bidirectional stale propagation
- 5 — `opencad_agent.api` (default port `8003`)
  - `GET /healthz`
  - `POST /chat`

## Frontend Runtime

- 4 — `opencad_viewport` runs as a separate React app.
- Mock geometry/solver mode is enabled by default (`VITE_USE_MOCK=true` behavior).
- Chat targets the live agent service by default; set `VITE_USE_CHAT_MOCK=true` only when you intentionally want mocked chat responses.
- Toggle the rest of the viewport to backend mode by setting `VITE_USE_MOCK=false` and configuring service URLs.

## Runtime Behavior Highlights

- Kernel registry never throws unhandled payload/lookup exceptions.
- Assembly mate operations validate entity references against the shape store before creation.
- Duplicate mates (same type between same entities) are rejected with `MATE_DUPLICATE`.
- Tree DAG validation rejects missing parent dependencies and self-dependencies.
- Tree rebuild IDs in API mock kernel are deterministic and parent-lineage aware.
- Assembly mate feature nodes go stale when either constrained shape rebuilds.
- Solver backend auto-selects SolveSpace when available, falls back to Python.
- Solver pre-validates malformed constraint references before optimization.
- `POST /sketch/diagnose` returns full Jacobian sparsity and DOF analysis.
- Agent planning executes tool sequences and returns structured operation logs.

## Suggested Deploy Shape

- Reverse proxy routes:
  - `/kernel/* -> 8000`
  - `/solver/* -> 8001`
  - `/tree/* -> 8002`
  - `/agent/* -> 8003`
- Serve `opencad_viewport` static bundle from CDN or edge cache.
- Solver backend: set `OPENCAD_SOLVER_BACKEND=auto` (or `solvespace` if
  `python-solvespace` is installed in the deploy image).

## Security and Exposure

- Disable docs/OpenAPI routes in production: `OPENCAD_ENABLE_DOCS=false`.
- Restrict browser origins with `OPENCAD_CORS_ALLOW_ORIGINS`.
- Keep services private behind a gateway; expose only intended public routes.
- Terminate TLS at the edge and enforce authentication/authorization there.
- Never commit `.env` files, secrets, or private datasets.

## Phase 2 — Topology Reference Stability

Part-level 3-D constraints require a topology reference strategy.
See [TOPOLOGY.md](TOPOLOGY.md) for the problem statement, prior-art analysis,
failure-mode checklist, and community proposal template.
This is an open research question and contribution opportunity.

## Verification

```bash
pytest


```

## 4 – Viewport Validation (manual)

```bash
cd opencad_viewport
npm install
npm run dev
```

Validate:
- viewport renders mock mesh
- feature tree selection highlights shapes
- sketch overlay shows icons and solve status
- chat panel streams response and operation statuses
- chat requests always generate and execute validated LLM code
