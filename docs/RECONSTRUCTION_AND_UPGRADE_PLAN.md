# OpenCAD Reconstruction and Upgrade Plan

Date: 2026-04-24
Release target: 0.1.1

This note records what was reconstructed locally, what the system is strong at, where it is weak, and where CAID can upgrade it into a useful CAD/simulation platform instead of a demo-shaped codebase.

## Local Reconstruction Status

OpenCAD now resolves as a normal editable Python package on this machine:

```powershell
uv sync --extra test --extra server
uv run --no-sync python -c "import opencad; print(opencad.__version__, opencad.__file__)"
opencad --help
```

The package layout is now aligned with the actual repository structure:

- Python packages live under `apps/backend/`.
- Pytest uses `apps/backend` as its import root.
- The editable install maps package discovery to `apps/backend`.
- `python-dotenv` is declared because the API modules import it directly.
- The OCCT extra now depends on `cadquery-ocp`, which is the package that provides the `OCP` import.
- The service modules expose standalone `FastAPI` apps while still exporting routers for the aggregate backend.
- Agent and example tests now resolve the real repository root before loading `examples/`.

Verification:

```powershell
uv run --no-sync python -m pytest
cd apps/opencad_viewport
pnpm install
pnpm test
pnpm build
```

Result:

```text
229 passed, 17 skipped
viewport tests: 3 passed
viewport build: passed
```

The earlier failures were not CAD logic failures. They came from running pytest inside a restricted sandbox that could create files but could not delete temporary files. Running with normal filesystem permissions passed the suite.

## System Shape

OpenCAD is a modular CAD platform with five main pieces:

- `opencad` is the headless user API and CLI. It exposes `Part`, `Sketch`, feature-tree logging, script execution, and export commands.
- `opencad_kernel` is the geometry operation layer. It validates typed operation payloads, stores shape metadata, logs operations, and can delegate to an OCCT/CadQuery backend.
- `opencad_solver` is a 2D sketch constraint solver with SolveSpace integration when available and a Python fallback.
- `opencad_tree` is the parametric feature-tree service. It owns dependency ordering, stale propagation, rebuild behavior, and expression evaluation.
- `opencad_agent` is the planning/chat layer. It can plan tool calls, execute operations, and optionally generate Python scripts through LiteLLM.
- `opencad_viewport` is the React/Three.js frontend. It can run in mock mode or target the backend APIs.

The aggregate backend at `apps/backend/api.py` mounts the kernel, solver, tree, and agent routers under separate prefixes. The individual service APIs can also run independently.

## What Is Good

The best part of OpenCAD is its boundaries. Kernel operations, solver operations, feature-tree operations, and agent operations are separated well enough that each can be replaced or strengthened without rewriting the whole system.

The operation registry is also a strong design choice. Operations have Pydantic schemas, version tags, validation errors, timing, and an operation log. That gives CAID a path toward replay, auditing, regression tests, and eventually deterministic design histories.

The analytic kernel fallback is useful for tests and product workflows that need fast metadata behavior before real B-rep geometry is available. It lets the CLI, tree, agent, and API layers be tested without requiring OpenCASCADE on every machine.

The OCCT boundary is real enough to be valuable. The backend protocol names the right capabilities: primitives, booleans, sketches, extrude, revolve, sweep, loft, patterns, STEP I/O, tessellation, and topology maps.

The fluent API is a good product surface. Scripts like `Part().extrude(...).fillet(...).export(...)` are a natural bridge between human-authored Python, generated agent code, and reproducible CAD build logs.

The feature tree has the right conceptual pieces: DAG ordering, dependency tracking, stale marking, rebuild, and expression evaluation. That is the right foundation for parametric design.

The test suite is broader than a toy project. It covers kernel operations, error paths, API routes, tree behavior, expressions, solver behavior, agent behavior, CLI behavior, examples, and the fluent API.

## What Is Bad

The repository originally looked installable, but was not wired to its actual layout. `pyproject.toml` pointed pytest and setuptools at the wrong import root. That made fresh local setup fail before reaching product behavior.

The API modules were internally inconsistent. The README described running `opencad_kernel.api:app`, `opencad_solver.api:app`, `opencad_tree.api:app`, and `opencad_agent.api:app`, but several modules only exposed routers. Tests expected apps. This is now fixed locally, but it shows the service contract was drifting.

The default analytic kernel can give a false sense of CAD correctness. It computes bounding boxes, approximate volumes, synthetic edges/faces, and mock STEP files. That is useful for orchestration, but it is not a reliable solid-modeling result.

The frontend defaults to mock data for much of the experience. That is productive for UI development, but dangerous if demos do not clearly distinguish mock geometry from live backend geometry.

The agent is more of a structured planner/tool runner than a trustworthy CAD engineer. It can help produce operations or code, but it does not yet prove manufacturability, simulation readiness, or geometric validity.

Production hardening is thin. CORS is permissive in the aggregate backend, services use in-memory stores, there is no auth layer in the app itself, and no durable design persistence.

SimCorrect currently depends on its own small `opencad.py` shim rather than this OpenCAD package. That means the two repos share an idea, not an integration contract.

## What Is Ugly

Topology naming is still the hard problem. The project has topology maps and selector ideas, but stable references across feature edits are not solved. Any serious parametric CAD system eventually lives or dies on whether downstream fillets, holes, mates, and constraints survive upstream edits.

Generated or executed Python CAD scripts are powerful but risky. They need sandboxing, deterministic runtime boundaries, dependency controls, output validation, and clear separation between trusted design code and generated code.

Mock STEP export in the analytic backend writes `OPENCAD-MOCK` data, not real neutral CAD geometry. This is fine for tests, but ugly if a caller expects an actual STEP pipeline.

There are multiple identities for the same system: standalone services, aggregate API, fluent Python API, operation registry, frontend mocks, and SimCorrect's shim. Without one canonical contract, integrations will keep drifting.

The backend package is under `apps/backend/`, the frontend is under `apps/opencad_viewport/`, and the working service entry points are package-qualified modules rather than a generic API module import from an unrelated working directory.

## Upgrade Direction

The highest-value upgrade is to make OpenCAD the shared geometry contract between the company repos. SimCorrect should stop carrying a separate OpenCAD-shaped shim and instead consume a small, stable CAID design artifact produced by OpenCAD.

Recommended artifact boundary:

```text
OpenCAD script or feature tree
  -> validated design artifact
  -> real geometry export or MJCF-oriented geometry description
  -> SimCorrect simulation scenes
  -> correction output as parameter changes or feature-tree patches
```

The correction loop should operate on named parameters and feature IDs, not raw mesh edits. That gives SimCorrect a path to say "hole spacing is wrong" or "link length needs +4 mm" and send a patch back to the parametric model.

OpenCAD 0.1.1 now includes the first version of that contract:

- `DesignArtifact` stores the feature tree, named design parameters, and simulation tags.
- `DesignPatch` stores structured parameter patches from SimCorrect.
- `Part.export_design_artifact(...)` writes the JSON handoff file.
- `apply_design_patch(...)` applies parameter patches without mutating the original artifact.

The first intended golden mapping is `forearm_length` in the CAID artifact to `link2_length` inside SimCorrect Problem 1.

## Priority Plan

Phase 1: make the repo boring to run.

- Keep the packaging fixes in place.
- Update README commands to match the actual package layout.
- Add CI for Python tests and frontend tests.
- Make the aggregate API use the shared app factory and production CORS settings.
- Add a single smoke command that checks import, CLI, API app construction, and an example script.

Phase 2: make geometry truth explicit.

- Rename or label analytic outputs as metadata/mock outputs wherever they can be mistaken for real CAD.
- Make OCCT the required backend for real STEP export, tessellation, and physical simulation handoff.
- Add backend capability reporting so callers know whether they are using analytic or OCCT behavior.
- Add golden tests for real STEP export/import when OCCT dependencies are installed.

Phase 3: connect OpenCAD and SimCorrect.

- Replace the SimCorrect shim with an adapter around the real `opencad` package.
- Define a versioned CAID design artifact with feature IDs, named parameters, geometry references, and simulation tags.
- Generate MuJoCo/MJCF geometry from OpenCAD artifacts through a dedicated exporter.
- Teach SimCorrect corrections to return parameter patches against the artifact.

Phase 4: harden parametric CAD behavior.

- Treat topology naming as a first-class project, not a helper function.
- Add persistent feature trees and operation logs.
- Add migration/version handling for operation schemas.
- Add rebuild diagnostics that identify which upstream change broke a downstream feature.
- Expand assembly mates from stored declarations into solved 3D constraints.

Phase 5: make the agent safe and useful.

- Validate every generated operation against schemas before execution.
- Run generated scripts in a restricted execution environment.
- Require artifact-level checks before export: manifoldness, nonzero volume, tolerances, named outputs, and simulation tags.
- Teach the agent to propose parameter patches instead of rewriting whole models.

## Near-Term CAID Contribution Opportunities

The most useful near-term contribution is not adding more CAD operations. It is making the system honest and connected:

- one install path,
- one backend contract,
- one design artifact,
- one real geometry mode,
- one SimCorrect integration path,
- one smoke-test command proving the loop still works.

Once that exists, new CAD operations, better solvers, and better agent behavior will have a stable place to land.
