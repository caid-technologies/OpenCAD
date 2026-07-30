# CAID Artifact Contract

Schema version: `1`

The CAID artifact is the stable boundary between OpenCAD and SimCorrect. OpenCAD owns design artifacts and applies design patches. SimCorrect consumes artifacts, identifies simulation faults, and returns patches against named design parameters.

Machine-readable schemas:

- [`schemas/caid-design-artifact-v1.schema.json`](schemas/caid-design-artifact-v1.schema.json)
- [`schemas/caid-design-patch-v1.schema.json`](schemas/caid-design-patch-v1.schema.json)

## Design Artifact

Required top-level fields:

```json
{
  "schema_version": 1,
  "artifact_id": "simcorrect-problem1-forearm",
  "producer": {"name": "opencad", "version": "0.1.1"},
  "created_at": "2026-04-24T00:00:00Z",
  "feature_tree": {"root_id": "root", "nodes": {}},
  "parameters": {},
  "simulation_tags": []
}
```

`artifact_id` is the identity used to reject patches for the wrong design. `feature_tree` is the OpenCAD reconstruction history. `parameters` contains the design-level values SimCorrect may patch.

Each parameter is keyed by name and must contain a matching `name` and a `value`:

```json
{
  "forearm_length": {
    "name": "forearm_length",
    "value": 0.25,
    "unit": "m",
    "role": "geometry",
    "feature_id": "feat-forearm"
  }
}
```

## Simulation Tags

Simulation tags map design names to simulator names without hardcoding aliases in diagnosis code.

```json
{
  "name": "forearm_length",
  "kind": "parameter",
  "target": "link2_length"
}
```

For schema version `1`, SimCorrect uses `kind="parameter"` tags to resolve an identified simulation parameter such as `link2_length` back to an OpenCAD parameter such as `forearm_length`.

## Design Patch

Patch payloads are structured JSON:

```json
{
  "schema_version": 1,
  "artifact_id": "simcorrect-problem1-forearm",
  "source": "simcorrect",
  "parameter_patches": [
    {
      "name": "forearm_length",
      "old_value": 0.25,
      "value": 0.30,
      "reason": "sensitivity_analysis identified link2_length."
    }
  ]
}
```

Patch rules:

- `schema_version` must match the supported contract version.
- `artifact_id` must match the artifact being patched.
- `parameter_patches` must contain at least one item.
- `name` must identify an existing design parameter.
- `old_value`, when present and non-null, must match the current artifact value.
- Applying a patch must not mutate the original artifact object in memory.

The `old_value` check is intentionally strict. It catches stale SimCorrect corrections before they overwrite a newer OpenCAD design state.

## Current Golden Slice

The first validated slice is SimCorrect Problem 1:

- OpenCAD parameter: `forearm_length`
- SimCorrect target: `link2_length`
- Expected patch: `forearm_length` from `0.25` to `0.30`

OpenCAD covers this with `apps/backend/opencad/tests/test_caid_golden_loop.py`. SimCorrect covers the corresponding fixture with `tests/test_golden_loop_fixture.py`.
