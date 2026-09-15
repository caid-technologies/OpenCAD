"""Isolate native process-exit failures; never turn a failed child into success."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "test_occt.py"


def main() -> int:
    probes = [
        ("python-ok", ["-c", "print('plain python complete')"], 0),
        ("python-failure", ["-c", "raise SystemExit(7)"], 7),
        ("ocp-import", ["-c", "import OCP; print('OCP imported')"], 0),
        ("cadquery-import", ["-c", "import cadquery; print('CadQuery imported')"], 0),
        ("cadquery-exit-zero", ["-c", "import cadquery; raise SystemExit(0)"], 0),
        ("native-preflight", ["-c", "from scripts.test_occt import native_preflight; native_preflight()"], 0),
        ("smoke", [str(RUNNER), "--smoke"], 0),
        ("legacy-native", ["-m", "pytest", "packages/opencad/tests/kernel/test_occt_backend.py", "--capture=sys", "-q"], 0),
        ("new-workflows", ["-m", "pytest", "packages/opencad/tests/occt/test_workflows.py", "--capture=sys", "-q"], 0),
        ("known-regressions", ["-m", "pytest", "packages/opencad/tests/occt/test_regressions.py", "--capture=sys", "-q"], 0),
        ("full-natural-return", ["-c", "from scripts.test_occt import main; code=main([]); print(f'Natural-return status: {code}', flush=True);\nif code: raise SystemExit(code)"], 0),
    ]
    records = []
    env = {**os.environ, "PYTHONFAULTHANDLER": "1"}
    for name, args, expected in probes:
        print(f"\n=== {name} ===", flush=True)
        started = time.perf_counter()
        try:
            process = subprocess.run(
                [sys.executable, "-X", "faulthandler", *args], cwd=ROOT, env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
            )
            record = {"name": name, "expected": expected, "returncode": process.returncode,
                      "stdout": process.stdout, "stderr": process.stderr,
                      "seconds": round(time.perf_counter() - started, 3)}
        except subprocess.TimeoutExpired:
            record = {"name": name, "expected": expected, "returncode": None, "error": "timeout"}
        records.append(record)
        print(json.dumps(record, ensure_ascii=True), flush=True)
    output = ROOT / "test-results" / "process-diagnostics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"executable": sys.executable, "python": sys.version, "probes": records}, indent=2), encoding="utf-8")
    return int(any(item["returncode"] != item["expected"] for item in records))


if __name__ == "__main__":
    raise SystemExit(main())
