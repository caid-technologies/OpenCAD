# OCCT testing

Native CAD coverage is separate from the fast analytic/workspace jobs. The
analytic backend is useful for contracts and DAG tests, but cannot certify
B-rep geometry. `.github/workflows/occt.yml` runs a native-only job on Linux
and Windows for every pull request and push to main. Repository maintainers
must separately select these status checks in branch protection/rulesets if
they want GitHub to require them before merging.

## Run locally

From the repository root, create an isolated environment and install only the
editable core and the native extra (no agent, web server, renderer, or LLM):

```bash
uv venv --python 3.11
uv pip install --python .venv -e "./packages/opencad[occt]" "pytest>=8,<10"
uv run --no-project --no-sync --python .venv python scripts/test_occt.py --smoke
uv run --no-project --no-sync --python .venv python scripts/test_occt.py --junitxml=test-results/occt.xml
```

Alternatively activate `.venv` and use `python scripts/test_occt.py` directly.
The workflow uses the setup-python interpreter on disposable runners.

The smoke suite checks native primitive volumes, translation, partially
overlapping booleans, and invalid-input state preservation. The full suite
also includes the existing native tests, sketches on all principal planes,
negative/symmetric extrusions, multi-hole profiles, fillet/chamfer material
removal, shell thickness, revolve/sweep/loft, pattern body counts and placement,
mesh indices/triangle areas, fresh-kernel STEP/STP round trips, and extrusion
parameter edits. Existing STL import/export coverage remains in the legacy
native module. This is not exhaustive coverage of every operation or format.

Focus or promote known regressions to release blockers:

```bash
python scripts/test_occt.py -k 'roundtrip or rebuild'
python scripts/test_occt.py --strict-regressions
python -m pytest scripts/tests/test_occt_runner.py
```

## No false-green native runs

The runner imports CadQuery/OCP and builds a real valid OCCT box before pytest.
Missing packages, broken DLLs, or failed native initialization exit nonzero.
Plain skipped tests (including collection skips), empty selections, and runs
without a test body cannot pass the native gate. The normal package tests may
still skip native tests on machines without OCCT; use the runner in native CI.
JUnit reports, slow-test timings, and resolved dependency versions are kept as
CI artifacts. Dependency resolution follows the package's supported ranges;
this is not a fully locked dependency job. The captured environment identifies
what was actually tested.

## Known defects are visible debt

Five regression cases currently carry strict expected-failure marks:

| ID | Desired behavior | Existing defect |
| --- | --- | --- |
| OCCT-001 | A drafted face yields valid, geometrically tapered solid geometry | Native call passes `gp_Pnt` instead of a neutral `gp_Pln` |
| OCCT-002 | `edges="top"` selects geometrically top edges | Selects first four enumerated edges |
| OCCT-003-sweep | Changed section is resolved to its rebuilt native shape | `profile_id` / `path_id` are absent from reference resolution |
| OCCT-003-loft | Changed sections rebuild a correctly sized loft | `profile_ids` list is not resolved |
| OCCT-004 | Reloaded tree creates real geometry in an empty kernel | Saved `built` nodes are skipped during rebuild |

These are tests, **not fixes**. Default CI reports them as XFAIL and prints an
explicit known-defect summary. Setup/control assertions run before applying the
expected-failure mark. Unexpected errors and strict XPASS results fail the run.
After repairing an operation, remove its mark; do not weaken the assertion.
`--strict-regressions` passes `--runxfail` and makes all five ordinary blockers.
No claim of full operation correctness should be based on a run with XFAILs.

## Performance and isolation

Native imports happen once per process. The smoke path avoids files and mesh
work; the full path avoids rendering, network access, and expensive generated
examples. Fixtures allocate fresh kernels and runtimes for each test. Native
objects are not session-cached: triangulation and mutable stores make that an
unsafe speed optimization. UUID shape IDs prevent accidental equality with
feature-node IDs from hiding reference-resolution failures.

CI caches dependency downloads and cancels superseded PR runs. Native tests
run serially by default to avoid multiplying OCCT memory use and oversubscribing
native thread pools. Use recorded durations to justify later parallelization;
no wall-clock speedup is claimed without a same-machine baseline.

Compare geometry with explicit dimensional/volume tolerances and expected
solid counts, never raw STEP bytes, face order, or unstable topology hashes.
