"""Tests for the native CI gate; these do not require OpenCAD or OCCT."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "test_occt.py"
spec = importlib.util.spec_from_file_location("occt_runner_under_test", RUNNER)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize("source,expected", [
    ("def test_ok(): assert True", 0),
    ("def test_bad(): assert False", 1),
    ("import pytest\ndef test_skip(): pytest.skip('absent native library')", 1),
    ("import pytest\npytest.skip('module absent', allow_module_level=True)", 5),
    ("import pytest\n@pytest.mark.xfail(strict=True, reason='known defect')\ndef test_known(): assert False", 0),
    ("import pytest\n@pytest.mark.xfail(strict=True, reason='fixed defect')\ndef test_fixed(): assert True", 1),
    ("import pytest\ndef test_ok(): assert True\ndef test_skip(): pytest.skip('must not pass')", 1),
    ("import pytest\n@pytest.fixture\ndef broken(): raise RuntimeError('setup failed')\ndef test_setup(broken): pass", 1),
    ("import pytest\ndef test_dynamic(request):\n request.node.add_marker(pytest.mark.xfail(strict=True, raises=AssertionError, reason='known'))\n assert False", 0),
])
def test_gate_in_real_pytest_process(tmp_path, source, expected):
    test_path = tmp_path / "test_probe.py"
    test_path.write_text(source, encoding="utf-8")
    code = (
        "import importlib.util, pytest; "
        f"s=importlib.util.spec_from_file_location('gate', {str(RUNNER)!r}); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        f"raise SystemExit(pytest.main([{str(test_path)!r}, '-q'], plugins=[m.NativeCoverageGate()]))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=45)
    assert result.returncode == expected, result.stdout + result.stderr


@pytest.mark.parametrize("exitstatus", [1, 2, 3, 4, 5])
def test_gate_preserves_existing_exit_status(exitstatus):
    session = SimpleNamespace(testscollected=0, exitstatus=exitstatus)
    runner.NativeCoverageGate().pytest_sessionfinish(session, exitstatus)
    assert session.exitstatus == exitstatus


def test_no_native_body_cannot_pass():
    session = SimpleNamespace(testscollected=2, exitstatus=0)
    runner.NativeCoverageGate().pytest_sessionfinish(session, 0)
    assert session.exitstatus == 1


def test_preflight_failure_stops_before_pytest(monkeypatch, capsys):
    def fail():
        raise ImportError("native DLL could not load")
    monkeypatch.setattr(runner, "native_preflight", fail)
    monkeypatch.setattr(runner.pytest, "main", lambda *a, **k: pytest.fail("tests must not run"))
    assert runner.main([]) == 2
    assert "native DLL could not load" in capsys.readouterr().err


@pytest.mark.parametrize("options,expected_count", [([], 2), (["--smoke"], 1)])
def test_runner_uses_fixed_native_paths(monkeypatch, options, expected_count):
    monkeypatch.setattr(runner, "native_preflight", lambda: None)
    recorded = []
    def invoke(args, plugins):
        recorded.extend(args)
        assert len(plugins) == 1 and isinstance(plugins[0], runner.NativeCoverageGate)
        return 0
    monkeypatch.setattr(runner.pytest, "main", invoke)
    assert runner.main(options) == 0
    paths = [arg for arg in recorded if arg.startswith(str(runner.NATIVE_TESTS))]
    assert len(paths) == expected_count


def test_strict_regressions_disable_expected_failures(monkeypatch):
    monkeypatch.setattr(runner, "native_preflight", lambda: None)
    def invoke(args, plugins):
        assert "--runxfail" in args
        return 1
    monkeypatch.setattr(runner.pytest, "main", invoke)
    assert runner.main(["--strict-regressions"]) == 1


def test_junit_directory_is_created(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "native_preflight", lambda: None)
    report = tmp_path / "reports" / "occt.xml"
    def invoke(args, plugins):
        assert f"--junitxml={report}" in args
        assert report.parent.is_dir()
        return 0
    monkeypatch.setattr(runner.pytest, "main", invoke)
    assert runner.main(["--junitxml", str(report)]) == 0


def test_negative_duration_count_is_invalid():
    with pytest.raises(SystemExit) as error:
        runner.main(["--durations", "-1"])
    assert error.value.code == 2


def test_native_capture_and_exit_status_are_preserved(monkeypatch, capsys):
    monkeypatch.setattr(runner, "native_preflight", lambda: None)
    def invoke(args, plugins):
        assert "--capture=sys" in args
        plugins[0].calls = 3
        return pytest.ExitCode.INTERNAL_ERROR
    monkeypatch.setattr(runner.pytest, "main", invoke)
    assert runner.main([]) == pytest.ExitCode.INTERNAL_ERROR
    output = capsys.readouterr().out
    assert "OCCT pytest exit=3; test bodies=3" in output
