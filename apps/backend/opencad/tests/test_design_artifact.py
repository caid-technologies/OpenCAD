from __future__ import annotations

from pathlib import Path

import pytest
from opencad import (
    DesignPatch,
    ParameterPatch,
    Part,
    Sketch,
    apply_design_patch,
    load_design_artifact,
    reset_default_context,
)
from pydantic import ValidationError


def test_part_exports_caid_design_artifact(tmp_path: Path) -> None:
    reset_default_context()
    part = Part(name="forearm").extrude(Sketch().rect(30, 4), depth=4)

    output = tmp_path / "caid-design.json"
    part.export_design_artifact(
        str(output),
        artifact_id="forearm-demo",
        parameters={
            "forearm_length": {
                "value": 0.30,
                "unit": "m",
                "role": "geometry",
                "feature_id": part.feature_id,
            }
        },
        simulation_tags=[
            {"name": "right_forearm", "kind": "body", "target": "r_forearm"},
            {"name": "forearm_length", "kind": "parameter", "target": "link2_length"},
        ],
    )

    artifact = load_design_artifact(output)

    assert artifact.schema_version == 1
    assert artifact.producer["version"] == "0.1.1"
    assert artifact.parameters["forearm_length"].value == 0.30
    assert artifact.parameter_values() == {"forearm_length": 0.30}
    assert len(artifact.simulation_tags) == 2
    assert any(node.operation == "extrude" for node in artifact.feature_tree.nodes.values())


def test_design_patch_updates_named_parameter(tmp_path: Path) -> None:
    reset_default_context()
    Part(name="forearm").box(30, 4, 4).export_design_artifact(
        str(tmp_path / "design.json"),
        artifact_id="forearm-demo",
        parameters={"forearm_length": {"value": 0.25, "unit": "m"}},
    )
    artifact = load_design_artifact(tmp_path / "design.json")
    patch = DesignPatch(
        artifact_id="forearm-demo",
        parameter_patches=[
            ParameterPatch(
                name="forearm_length",
                old_value=0.25,
                value=0.30,
                reason="SimCorrect isolated forearm length error.",
            )
        ],
    )

    updated = apply_design_patch(artifact, patch)

    assert artifact.parameters["forearm_length"].value == 0.25
    assert updated.parameters["forearm_length"].value == 0.30


def test_design_patch_rejects_stale_old_value(tmp_path: Path) -> None:
    reset_default_context()
    Part(name="forearm").box(30, 4, 4).export_design_artifact(
        str(tmp_path / "design.json"),
        artifact_id="forearm-demo",
        parameters={"forearm_length": {"value": 0.25, "unit": "m"}},
    )
    artifact = load_design_artifact(tmp_path / "design.json")
    patch = DesignPatch(
        artifact_id="forearm-demo",
        parameter_patches=[
            ParameterPatch(
                name="forearm_length",
                old_value=0.20,
                value=0.30,
            )
        ],
    )

    with pytest.raises(ValueError, match="expected old value"):
        apply_design_patch(artifact, patch)


def test_design_patch_requires_at_least_one_parameter_patch() -> None:
    with pytest.raises(ValidationError):
        DesignPatch(artifact_id="forearm-demo", parameter_patches=[])
