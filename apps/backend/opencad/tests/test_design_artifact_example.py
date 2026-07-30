from __future__ import annotations

import runpy
from pathlib import Path

from opencad import load_design_artifact


def test_simcorrect_forearm_example_writes_artifact(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    monkeypatch.chdir(tmp_path)

    runpy.run_path(str(repo_root / "examples" / "simcorrect_forearm_design.py"), run_name="__main__")

    artifact = load_design_artifact(tmp_path / "caid-design.json")
    assert artifact.artifact_id == "simcorrect-problem1-forearm"
    assert artifact.parameters["forearm_length"].value == 0.30
    assert any(tag.kind == "parameter" and tag.target == "link2_length" for tag in artifact.simulation_tags)
