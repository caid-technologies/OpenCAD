"""Run the real OCCT suite without allowing missing native coverage to pass.

This intentionally does not resolve the whole uv workspace: install the core
package with its occt extra and pytest in an isolated environment first.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE_TESTS = ROOT / "packages" / "opencad" / "tests"


class NativeCoverageGate:
    """Make an empty run, a plain skip, or a collection skip fail CI.

    Documented strict xfails remain visible debt, not evidence of working CAD.
    Use --strict-regressions to run those tests as ordinary release blockers.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.skipped: list[str] = []
        self.expected_failures: list[str] = []

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call":
            self.calls += 1
        if report.skipped:
            if getattr(report, "wasxfail", None):
                self.expected_failures.append(report.nodeid)
            else:
                self.skipped.append(report.nodeid)

    def pytest_collectreport(self, report) -> None:
        if report.skipped:
            self.skipped.append(report.nodeid)

    def pytest_sessionfinish(self, session, exitstatus) -> None:
        # Never overwrite an existing failure, interrupt, usage, or no-tests code.
        if exitstatus == pytest.ExitCode.OK and (
            session.testscollected == 0 or self.calls == 0 or self.skipped
        ):
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter) -> None:
        if self.skipped:
            terminalreporter.write_sep("=", "OCCT GATE FAILED: native tests skipped")
            for nodeid in sorted(set(self.skipped)):
                terminalreporter.write_line(nodeid)
        if self.calls == 0:
            terminalreporter.write_sep("=", "OCCT GATE FAILED: no native test bodies ran")
        if self.expected_failures:
            terminalreporter.write_sep(
                "=", f"OCCT known defects: {len(self.expected_failures)} (not fixed)"
            )
            terminalreporter.write_line(
                "Use --strict-regressions to treat these as release blockers."
            )


def native_preflight() -> None:
    """Import native libraries AND build a valid solid; find_spec is insufficient."""
    importlib.import_module("cadquery")
    prim = importlib.import_module("OCP.BRepPrimAPI")
    check = importlib.import_module("OCP.BRepCheck")
    shape = prim.BRepPrimAPI_MakeBox(1.0, 1.0, 1.0).Shape()
    if shape.IsNull() or not check.BRepCheck_Analyzer(shape).IsValid():
        raise RuntimeError("OCCT preflight did not produce a valid box")
    for distribution in ("cadquery", "cadquery-ocp", "casadi", "nlopt", "pytest"):
        print(f"{distribution}=={importlib.metadata.version(distribution)}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Run cheap native contracts only")
    parser.add_argument(
        "--strict-regressions", action="store_true",
        help="Disable expected-failure marks; known CAD defects fail the run",
    )
    parser.add_argument("--junitxml", type=Path)
    parser.add_argument("--durations", type=int, default=15)
    parser.add_argument("-k", dest="expression", help="Focus on matching native test names")
    args = parser.parse_args(argv)
    if args.durations < 0:
        parser.error("--durations must be nonnegative")

    try:
        native_preflight()
    except Exception as exc:
        print(
            f"OCCT preflight failed: {type(exc).__name__}: {exc}\n"
            'Install the core native extra and pytest, for example:\n'
            '  uv pip install --python .venv-occt -c scripts/occt-constraints.txt -e "./packages/opencad[occt]" "pytest>=8,<10"',
            file=sys.stderr,
        )
        return 2

    paths = [NATIVE_TESTS / "occt" / "test_smoke.py"] if args.smoke else [
        NATIVE_TESTS / "kernel" / "test_occt_backend.py",
        NATIVE_TESTS / "occt",
    ]
    pytest_args = [
        *(str(path) for path in paths),
        "-ra", "--strict-markers", "--capture=sys", f"--durations={args.durations}",
    ]
    if args.strict_regressions:
        pytest_args.append("--runxfail")
    if args.expression:
        pytest_args.extend(["-k", args.expression])
    if args.junitxml:
        args.junitxml.parent.mkdir(parents=True, exist_ok=True)
        pytest_args.append(f"--junitxml={args.junitxml}")
    # Native libraries own C/C++ stdout handles. Keep those descriptors stable
    # instead of swapping them into pytest temporary files on every test phase.
    # Python output is still captured; native diagnostics stream to the CI log.
    gate = NativeCoverageGate()
    status = int(pytest.main(pytest_args, plugins=[gate]))
    print(
        f"OCCT pytest exit={status}; test bodies={gate.calls}; "
        f"plain skips={len(gate.skipped)}; known defects={len(gate.expected_failures)}",
        flush=True,
    )
    return status


if __name__ == "__main__":
    raise SystemExit(main())
