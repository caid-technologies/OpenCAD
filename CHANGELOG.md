# Changelog

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
