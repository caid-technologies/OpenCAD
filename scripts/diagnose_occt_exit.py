"""Verify native initialization AND process shutdown in isolated interpreters.

The parent deliberately imports no native libraries. A child that prints a
successful result but crashes at shutdown must still fail this check.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "test_occt.py"


class Probe(NamedTuple):
    name: str
    arguments: tuple[str, ...]
    expected: int = 0


def build_probes(full: bool = False) -> list[Probe]:
    probes = [
        Probe("ocp-import", ("-c", "import OCP; print('OCP imported')")),
        Probe("nlopt-casadi", ("-c", "import nlopt, casadi; print('pair imported')")),
        Probe("casadi-nlopt", ("-c", "import casadi, nlopt; print('reverse pair imported')")),
        Probe("cadquery-import", ("-c", "import cadquery; print('CadQuery imported')")),
        Probe("native-preflight", ("-c", "from scripts.test_occt import native_preflight; native_preflight()")),
        # A native import must not erase an intentional nonzero exit either.
        Probe("cadquery-exit-seven", ("-c", "import cadquery; raise SystemExit(7)"), 7),
    ]
    if full:
        probes.extend([
            Probe("smoke", (str(RUNNER), "--smoke")),
            Probe("legacy-native", ("-m", "pytest", "packages/opencad/tests/kernel/test_occt_backend.py", "--capture=sys", "-q")),
            Probe("new-workflows", ("-m", "pytest", "packages/opencad/tests/occt/test_workflows.py", "--capture=sys", "-q")),
            Probe("known-regressions", ("-m", "pytest", "packages/opencad/tests/occt/test_regressions.py", "--capture=sys", "-q")),
            Probe("full-natural-return", ("-c", "from scripts.test_occt import main; code=main([]); print(f'Natural-return status: {code}', flush=True);\nif code: raise SystemExit(code)")),
        ])
    return probes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Also isolate each native test group")
    parser.add_argument("--report", type=Path, default=ROOT / "test-results" / "native-processes.json")
    args = parser.parse_args(argv)
    records = []
    failures = 0
    env = {**os.environ, "PYTHONFAULTHANDLER": "1", "PYTHONIOENCODING": "utf-8"}
    for probe in build_probes(args.full):
        started = time.perf_counter()
        try:
            process = subprocess.run(
                [sys.executable, "-X", "faulthandler", *probe.arguments], cwd=ROOT, env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
            )
            record = {"name": probe.name, "expected": probe.expected, "returncode": process.returncode,
                      "stdout": process.stdout, "stderr": process.stderr}
        except (subprocess.TimeoutExpired, OSError) as exc:
            record = {"name": probe.name, "expected": probe.expected, "returncode": None,
                      "error": f"{type(exc).__name__}: {exc}"}
        record["seconds"] = round(time.perf_counter() - started, 3)
        failures += record["returncode"] != probe.expected
        records.append(record)
        print(json.dumps(record, ensure_ascii=True), flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps({"executable": sys.executable, "python": sys.version, "probes": records}, indent=2),
        encoding="utf-8",
    )
    print(f"OCCT process checks: {len(records) - failures} passed, {failures} failed", flush=True)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
