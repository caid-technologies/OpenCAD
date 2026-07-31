# Contribution

## Development Setup

Use uv for Python and pnpm for the viewport.

```bash
uv sync --extra test --extra server
cd opencad_viewport
pnpm install
```

## Verification

Run these before proposing changes:

```bash
uv run --no-sync python -m pytest
cd opencad_viewport
pnpm test
pnpm build
```

## Integration Contract

OpenCAD owns the CAID design artifact:

- `DesignArtifact`: feature tree, named parameters, and simulation tags.
- `DesignPatch`: structured parameter updates from SimCorrect.
- `Part.export_design_artifact(...)`: writes the handoff JSON.

Keep this contract small, versioned, and test-covered. Do not add problem-specific fields until a SimCorrect problem needs them.

The written contract lives in `docs/CAID_ARTIFACT_CONTRACT.md`.

## Generated Files

Do not commit local virtualenvs, build outputs, mock STEP exports, or ad hoc generated artifacts unless they are intentional fixtures.
