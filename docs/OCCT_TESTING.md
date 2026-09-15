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
uv venv --python 3.11 .venv-occt
uv pip install --python .venv-occt -c scripts/occt-constraints.txt -e "./packages/opencad[occt]" "pytest>=8,<10"
uv run --no-project --python .venv-occt python scripts/test_occt.py --smoke
uv run --no-project --python .venv-occt python scripts/test_occt.py --junitxml=test-results/occt.xml
```

Alternatively activate `.venv-occt` and use `python scripts/test_occt.py` directly.
The workflow creates a dedicated `.venv-occt` with Python 3.11 on disposable
runners. This keeps dependencies out of the runner's system environment and
avoids cross-drive cache-to-environment copies on Windows hosts whose Python
installation is on C: but whose workspace/cache are on D:.

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
python -m pytest scripts/tests/test_occt_runner.py scripts/tests/test_occt_processes.py
```

## Windows native dependency compatibility

In [the PR #105 diagnostic run](https://github.com/caid-technologies/OpenCAD/actions/runs/34972608238),
`import OCP` exited normally, but `import cadquery` alone crashed on Windows
at interpreter shutdown with `0xC0000374` or `0xC0000005`. The failure occurred
without importing OpenCAD or running pytest. The successful test summary was
therefore not proof of a successful process. The child-process probes exposed
the native exit codes that the outer invocation had reported as exit 1.

[Upstream CadQuery report](https://github.com/CadQuery/cadquery/issues/1564#issuecomment-5532644183)
identifies the CasADi 3.8.0 / NLopt 2.11.0 Windows wheel interaction and reports
clean shutdown with CasADi 3.7.2. `scripts/occt-constraints.txt` applies that
specific compatibility pin **only on Windows**; Linux is not constrained by it.
Both CI and the local commands above consume the same constraint file.
This is a test-environment workaround, not a fix to either upstream binary.
It does not change the published OpenCAD dependency metadata or workspace lock.
It must not be interpreted as validation of the unconstrained Windows stack.

CI also runs six short child-process probes. These check OCP import, both
NLopt/CasADi import orders, CadQuery import, a real native preflight build,
and preservation of an intentional exit code 7 after a native import. The
parent imports no native libraries and checks each child's actual return code,
including shutdown. Crashes/timeouts fail; successful-looking stdout cannot
make them pass. JSON reports retain stdout, stderr, raw status, and timings.

```bash
uv run --no-project --python .venv-occt python scripts/diagnose_occt_exit.py
# Optional deeper diagnosis: also isolate the native test groups.
uv run --no-project --python .venv-occt python scripts/diagnose_occt_exit.py --full
```

Keep the constraint until an upstream replacement passes both import orders,
the native-build shutdown probe, and the full native suite on Windows. Never
use forced zero exits, `os._exit`, disabled crash handlers, or
`continue-on-error` to hide this failure. Fault reporting remains enabled.

## No false-green native runs

The runner imports CadQuery/OCP and builds a real valid OCCT box before pytest.
Missing packages, broken DLLs, or failed native initialization exit nonzero.
Plain skipped tests (including collection skips), empty selections, and runs
without a test body cannot pass the native gate. The normal package tests may
still skip native tests on machines without OCCT; use the runner in native CI.
JUnit reports, slow-test timings, and resolved dependency versions are kept as
CI artifacts. Dependency resolution follows the package's supported ranges
apart from the Windows compatibility pin; this is not a fully locked dependency
job. The captured environment identifies what was actually tested.

The native runner uses `--capture=sys`: Python output is captured, while C/C++
diagnostics stream directly to CI instead of redirecting native file handles.
It also prints pytest's returned exit code and coverage counts. That code is
preserved; a failed process must never be overridden just because its printed
assertion summary looks successful.

## Known defects are visible debt

Draft (OCCT-001, #106) is now a normal passing regression; see
[DRAFT.md](DRAFT.md) for the neutral-plane API and its native test coverage.
Four other regression cases still carry strict expected-failure marks:

| ID | Desired behavior | Existing defect |
| --- | --- | --- |
| OCCT-002 (#107) | `edges="top"` selects geometrically top edges | Selects first four enumerated edges |
| OCCT-003-sweep (#108) | Changed section is resolved to its rebuilt native shape | `profile_id` / `path_id` are absent from reference resolution |
| OCCT-003-loft (#109) | Changed sections rebuild a correctly sized loft | `profile_ids` list is not resolved |
| OCCT-004 (#110) | Reloaded tree creates real geometry in an empty kernel | Saved `built` nodes are skipped during rebuild |

These are tests, **not fixes**. Default CI reports them as XFAIL and prints an
explicit known-defect summary. Setup/control assertions run before applying the
expected-failure mark. Unexpected errors and strict XPASS results fail the run.
After repairing an operation, remove its mark; do not weaken the assertion.
`--strict-regressions` passes `--runxfail` and makes the remaining four ordinary blockers.
No claim of full operation correctness should be based on a run with XFAILs.

## Performance and isolation

Native imports happen once per process. Separate shutdown probes intentionally
use fresh processes; their startup costs are not included in pytest timings.
The smoke path avoids files and mesh work; the full path avoids rendering,
network access, and expensive generated examples. Fixtures allocate fresh
kernels and runtimes for each test. Native objects are not session-cached:
triangulation and mutable stores make that an unsafe speed optimization.
UUID shape IDs prevent accidental equality with feature-node IDs from hiding
reference-resolution failures.

CI caches dependency downloads and cancels superseded PR runs. Native tests
run serially by default to avoid multiplying OCCT memory use and oversubscribing
native thread pools. Use recorded durations to justify later parallelization;
no wall-clock speedup is claimed without a same-machine baseline.

Compare geometry with explicit dimensional/volume tolerances and expected
solid counts, never raw STEP bytes, face order, or unstable topology hashes.
