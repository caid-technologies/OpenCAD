"""The process check must detect crashes after apparently successful output."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "diagnose_occt_exit.py"
spec = importlib.util.spec_from_file_location("occt_process_check", SCRIPT)
process_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(process_check)


@pytest.mark.parametrize("returncode,expected,status", [
    (0, 0, 0), (7, 7, 0), (0, 7, 1), (1, 0, 1),
    (3221225477, 0, 1), (3221226356, 0, 1), (-11, 0, 1),
])
def test_checks_actual_process_status(monkeypatch, tmp_path, returncode, expected, status):
    probe = process_check.Probe("probe", ("-c", "print('done')"), expected)
    monkeypatch.setattr(process_check, "build_probes", lambda full: [probe])
    def run(command, **kwargs):
        assert command[:3] == [process_check.sys.executable, "-X", "faulthandler"]
        assert kwargs["cwd"] == process_check.ROOT
        assert kwargs["timeout"] == 90
        assert kwargs["env"]["PYTHONFAULTHANDLER"] == "1"
        return SimpleNamespace(returncode=returncode, stdout="68 passed\n", stderr="")
    monkeypatch.setattr(process_check.subprocess, "run", run)
    report = tmp_path / "nested" / "processes.json"
    assert process_check.main(["--report", str(report)]) == status
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["probes"][0]["returncode"] == returncode
    assert saved["probes"][0]["expected"] == expected


@pytest.mark.parametrize("error", [subprocess.TimeoutExpired("probe", 90), OSError("cannot start")])
def test_child_startup_failure_is_reported_and_remaining_probes_run(monkeypatch, tmp_path, error):
    probes = [process_check.Probe("first", ("-c", "")), process_check.Probe("second", ("-c", ""))]
    monkeypatch.setattr(process_check, "build_probes", lambda full: probes)
    calls = []
    def run(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise error
        return SimpleNamespace(returncode=0, stdout="complete", stderr="")
    monkeypatch.setattr(process_check.subprocess, "run", run)
    report = tmp_path / "processes.json"
    assert process_check.main(["--report", str(report)]) == 1
    records = json.loads(report.read_text(encoding="utf-8"))["probes"]
    assert len(calls) == 2
    assert records[0]["returncode"] is None
    assert type(error).__name__ in records[0]["error"]
    assert records[1]["returncode"] == 0


def test_default_probes_cover_native_shutdown_without_running_geometry_suite():
    probes = process_check.build_probes()
    assert len(probes) == 6
    assert {"nlopt-casadi", "casadi-nlopt", "cadquery-import", "native-preflight"} <= {p.name for p in probes}
    assert all(p.arguments[0] == "-c" for p in probes)
    assert next(p for p in probes if p.name == "cadquery-exit-seven").expected == 7


def test_full_diagnostics_add_all_groups():
    probes = process_check.build_probes(full=True)
    assert len(probes) == 11
    assert {"smoke", "legacy-native", "new-workflows", "known-regressions", "full-natural-return"} <= {p.name for p in probes}
    assert len({p.name for p in probes}) == len(probes)
