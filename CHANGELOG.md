# Changelog

## Unreleased

### Viewport split into a publishable npm package

`apps/opencad_viewport` was a Vite application — `private: true`, no entry
point, no types — so nothing in it could be consumed from npm. The components
are now a library:

- **`packages/opencad-viewport`** — npm package `opencad-viewport`. Ships
  `Viewport3D`, `FeatureTreePanel`, `SketchEditor`, `ChatPanel`,
  `CadFileToolbar`, `OpenCadApiClient`, the feature-tree helpers, the mock
  fixtures, and all view-model types, with generated `.d.ts` and an ES build.
- **`apps/opencad_viewport`** — reference app, still `private`, now just
  `index.html` + `App.tsx` + `main.tsx` consuming the library.

`react`, `react-dom`, `three`, `@react-three/fiber`, and `@react-three/drei`
are **peer dependencies** and stay external — bundling them causes
duplicate-instance failures (invalid hook calls, broken `instanceof` checks).
`axios` is external too, resolved from the dependency list.

The stylesheet is opt-in rather than a side effect of importing the entry:

```ts
import { Viewport3D } from "opencad-viewport";
import "opencad-viewport/styles.css";
```

Repository-level changes: a pnpm workspace at the root (the lockfile moved
from `apps/opencad_viewport/pnpm-lock.yaml`), the frontend Docker build now
takes the repository root as its context, and CI builds the library, builds
the app against it, and verifies the publishable tarball.

### Core modules nested under `opencad` (breaking)

The `opencad_` prefix restated the distribution name on every import, so the
three sibling packages became subpackages of `opencad` instead:

| Before | After |
|--------|-------|
| `opencad_kernel` | `opencad.kernel` |
| `opencad_solver` | `opencad.solver` |
| `opencad_tree` | `opencad.tree` |

```python
from opencad_kernel.client import KernelClient   # before
from opencad.kernel.client import KernelClient   # after
```

`from opencad import Part, Sketch` is unchanged. The distribution now ships a
single top-level name, `opencad`, so it claims nothing generic in
`site-packages`.

`opencad_agent` and `opencad_server` are unchanged; they belong to separate
distributions where the prefix identifies the project.

### Core split out of the backend (breaking)

The repository is now a uv workspace of three independently installable
distributions. The core no longer lives inside the backend application.

- `opencad` (`packages/opencad`) — kernel, solver, feature tree, fluent API, and
  CLI. Depends on pydantic and numpy only.
- `opencad-agent` (`packages/opencad-agent`) — the LLM agent. Depends on
  `opencad`; LiteLLM moved behind an `[llm]` extra.
- `opencad-backend` (`apps/backend`) — FastAPI transport, importable as
  `opencad_server`. The only distribution that depends on a web framework.

Migration:

- `uvicorn api:app --app-dir apps/backend` → `uvicorn opencad_server.app:app`
  (the `api:app` shim is gone).
- `uv sync --extra test --extra server` → `uv sync --all-packages --group test`.
- `pip install opencad` no longer installs FastAPI, httpx, python-dotenv, or the
  agent. Install `opencad-agent[llm]` or `opencad-backend` for those.
- `RuntimeContext.chat(message)` → `opencad_agent.run_chat(context, message)`,
  so the core no longer imports the agent.
- `RuntimeContext._sync_counters()` is now the public `sync_counters()`, and
  `adopt_tree()` replaces the tree plus its ID counters and cursors.
- CI runs a job per package with only that package's dependencies installed.

### HTTP layer separation

- All FastAPI routing moved out of the core packages; they no longer import
  FastAPI, Starlette, httpx, or python-dotenv.
- Added `opencad.kernel.client.KernelClient`, a transport-agnostic protocol with
  an in-process `LocalKernelClient`. The HTTP implementation
  (`opencad_server.http_kernel_client.HttpKernelClient`) is wired in at the
  composition root, replacing the ad-hoc httpx calls that lived in
  `opencad_agent.tools` and the feature-tree API.
- `RuntimeContext`, `OpenCadAgentService`, and `ToolRuntime` now take a
  `kernel_client` instead of `kernel_call`/`kernel_topology_call` callables.
- Moved `fastapi`, `httpx`, `python-dotenv`, and `uvicorn` into the backend
  distribution; they are no longer dependencies of the core.
- Added `apps/backend/tests/test_core_boundary.py`, which fails if any core
  module imports the web layer or a web/network library.

## 0.1.1 - 2026-04-24

- Fixed Python package discovery for the `apps/backend/` source layout.
- Added the missing `python-dotenv` runtime dependency.
- Corrected the OCCT optional dependency to use `cadquery-ocp`.
- Added a lightweight `server` extra for uv-based local service startup.
- Added a versioned CAID design artifact export and parameter patch model for SimCorrect integration.
- Restored standalone FastAPI app exports for the kernel, solver, feature-tree, and agent services.
- Fixed agent and example test path resolution against the real repository root.
- Installed and validated the viewport with pnpm, including a committed `pnpm-lock.yaml`.
- Updated developer commands to use pnpm for the viewport.
- Added a reconstruction and upgrade assessment under `docs/`.
