from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from opencad import (
    DesignArtifact,
    DesignPatch,
    Part,
    reset_default_context,
    validate_design_artifact_payload,
    validate_design_patch_payload,
)
from opencad.design_artifact import ARTIFACT_REQUIRED_KEYS, PATCH_REQUIRED_KEYS
from pydantic import ValidationError


def artifact_payload(tmp_path: Path) -> dict:
    reset_default_context()
    part = Part(name="forearm").box(30, 4, 4)
    path = tmp_path / "artifact.json"
    part.export_design_artifact(
        str(path),
        artifact_id="forearm-demo",
        parameters={"forearm_length": {"value": 0.25, "unit": "m", "feature_id": part.feature_id}},
        simulation_tags=[{"name": "forearm_length", "kind": "parameter", "target": "link2_length"}],
    )
    return DesignArtifact.model_validate_json(path.read_text(encoding="utf-8")).model_dump(mode="json")


def patch_payload() -> dict:
    return {
        "schema_version": 1,
        "artifact_id": "forearm-demo",
        "source": "simcorrect",
        "parameter_patches": [{"name": "forearm_length", "old_value": 0.25, "value": 0.30}],
    }


def test_schema_version_is_const_in_generated_schemas() -> None:
    artifact_schema = DesignArtifact.model_json_schema()
    patch_schema = DesignPatch.model_json_schema()

    assert artifact_schema["properties"]["schema_version"]["const"] == 1
    assert patch_schema["properties"]["schema_version"]["const"] == 1
    assert patch_schema["properties"]["parameter_patches"]["minItems"] == 1


def test_committed_json_schemas_expose_required_contract_keys(repo_root: Path) -> None:
    artifact_schema = json.loads(
        (repo_root / "docs" / "schemas" / "caid-design-artifact-v1.schema.json").read_text(encoding="utf-8")
    )
    patch_schema = json.loads(
        (repo_root / "docs" / "schemas" / "caid-design-patch-v1.schema.json").read_text(encoding="utf-8")
    )

    assert set(artifact_schema["required"]) == ARTIFACT_REQUIRED_KEYS
    assert set(patch_schema["required"]) == PATCH_REQUIRED_KEYS
    assert artifact_schema["properties"]["schema_version"]["const"] == 1
    assert patch_schema["properties"]["schema_version"]["const"] == 1
    assert "anyOf" in artifact_schema["$defs"]["parameter_value"]
    assert "oneOf" not in artifact_schema["$defs"]["parameter_value"]
    assert "anyOf" in patch_schema["$defs"]["parameter_patch"]["properties"]["value"]
    assert "oneOf" not in patch_schema["$defs"]["parameter_patch"]["properties"]["value"]


def test_external_artifact_payload_requires_full_contract_envelope(tmp_path: Path) -> None:
    payload = artifact_payload(tmp_path)
    del payload["simulation_tags"]

    with pytest.raises(ValueError, match="missing required key"):
        validate_design_artifact_payload(payload)


def test_external_patch_payload_requires_source() -> None:
    payload = patch_payload()
    del payload["source"]

    with pytest.raises(ValueError, match="missing required key"):
        validate_design_patch_payload(payload)


def test_artifact_rejects_parameter_key_name_mismatch(tmp_path: Path) -> None:
    payload = artifact_payload(tmp_path)
    mismatch = deepcopy(payload)
    mismatch["parameters"]["forearm_length"]["name"] = "other_length"

    with pytest.raises(ValidationError, match="does not match parameter name"):
        DesignArtifact.model_validate(mismatch)


def test_patch_rejects_unsupported_schema_version() -> None:
    payload = patch_payload()
    payload["schema_version"] = 2

    with pytest.raises(ValidationError):
        DesignPatch.model_validate(payload)
