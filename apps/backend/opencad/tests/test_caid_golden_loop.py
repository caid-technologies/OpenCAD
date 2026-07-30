from __future__ import annotations

from pathlib import Path

from opencad import Part, Sketch, apply_design_patch, load_design_artifact, reset_default_context


def test_caid_golden_forearm_patch_round_trip(tmp_path: Path) -> None:
    reset_default_context()
    part = Part(name="forearm").extrude(Sketch().rect(30, 4), depth=4)
    artifact_path = tmp_path / "caid-design.json"
    part.export_design_artifact(
        str(artifact_path),
        artifact_id="simcorrect-problem1-forearm",
        parameters={
            "forearm_length": {
                "value": 0.25,
                "unit": "m",
                "role": "geometry",
                "feature_id": part.feature_id,
            }
        },
        simulation_tags=[
            {"name": "forearm_length", "kind": "parameter", "target": "link2_length"},
        ],
    )
    artifact = load_design_artifact(artifact_path)
    simcorrect_patch = {
        "schema_version": 1,
        "artifact_id": "simcorrect-problem1-forearm",
        "source": "simcorrect",
        "parameter_patches": [
            {
                "name": "forearm_length",
                "old_value": 0.25,
                "value": 0.30,
                "reason": "sensitivity_analysis identified link2_length.",
            }
        ],
    }

    updated = apply_design_patch(artifact, simcorrect_patch)

    assert artifact.parameters["forearm_length"].value == 0.25
    assert updated.parameters["forearm_length"].value == 0.30
    assert updated.simulation_tags == artifact.simulation_tags
