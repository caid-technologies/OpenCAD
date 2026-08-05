# Contribution

## Development Setup

Use uv for Python and pnpm for the viewport. Both are workspaces, so install
from the repository root.

```bash
uv sync --all-packages --all-extras --group test
pnpm install
```

Omitting `--all-extras` leaves the OCCT B-rep backend uninstalled, and the
kernel then falls back to the analytic backend, which cannot export STEP.

To work on a single Python package with only its own dependencies present:

```bash
uv sync --package opencad --extra occt --group test          # core alone, no web stack
uv sync --package opencad-agent --group test                 # core + agent
uv sync --package opencad-backend --extra occt --group test  # everything
```

## Verification

Run these before proposing changes:

```bash
uv run --no-sync python -m pytest
pnpm --filter opencad-viewport test
pnpm --filter opencad-viewport build
pnpm --filter opencad-viewport-app build
```

## Layout

Libraries live under `packages/` and are published; applications live under
`apps/` and are not.

| Path | Distribution | Notes |
|------|--------------|-------|
| `packages/opencad` | `opencad` (PyPI) | kernel, solver, tree, fluent API, CLI |
| `packages/opencad-agent` | `opencad-agent` (PyPI) | LLM agent; depends on `opencad` |
| `packages/opencad-viewport` | `opencad-viewport` (npm) | React components |
| `apps/backend` | `opencad-backend` (PyPI) | FastAPI transport |
| `apps/opencad_viewport` | — | reference app, private |

The dependency arrow runs core ← agent ← backend and never reverses. The core
packages must not import FastAPI, Starlette, httpx, uvicorn, python-dotenv, or
`opencad_server`; `apps/backend/tests/test_core_boundary.py` enforces this, and
CI runs a job per package with only that package's dependencies installed.

Cross-package versions move in lockstep and are pinned exactly
(`opencad==0.2.0`), because uv's workspace sources are dev-only metadata that
never reach a published wheel.

## Integration Contract

OpenCAD owns the CAID design artifact:

- `DesignArtifact`: feature tree, named parameters, and simulation tags.
- `DesignPatch`: structured parameter updates from SimCorrect.
- `Part.export_design_artifact(...)`: writes the handoff JSON.

Keep this contract small, versioned, and test-covered. Do not add problem-specific fields until a SimCorrect problem needs them.

The written contract lives in `docs/CAID_ARTIFACT_CONTRACT.md`.

## Generated Files

Do not commit local virtualenvs, build outputs, mock STEP exports, or ad hoc generated artifacts unless they are intentional fixtures.
