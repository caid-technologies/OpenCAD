from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Literal, Self

from pydantic import BaseModel, Field, model_validator

from opencad.version import __version__
from opencad_tree.models import FeatureTree

if TYPE_CHECKING:
    from opencad.runtime import RuntimeContext

ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_REQUIRED_KEYS = frozenset(
    {"schema_version", "artifact_id", "producer", "created_at", "feature_tree", "parameters", "simulation_tags"}
)
PATCH_REQUIRED_KEYS = frozenset({"schema_version", "artifact_id", "source", "parameter_patches"})

ParameterValue = bool | int | float | str
SimulationKind = Literal["body", "joint", "geom", "site", "parameter"]


class DesignParameter(BaseModel):
    name: str
    value: ParameterValue
    unit: str | None = None
    role: str | None = None
    feature_id: str | None = None


class SimulationTag(BaseModel):
    name: str
    kind: SimulationKind
    target: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParameterPatch(BaseModel):
    name: str
    value: ParameterValue
    old_value: ParameterValue | None = None
    reason: str | None = None


class DesignPatch(BaseModel):
    schema_version: Literal[ARTIFACT_SCHEMA_VERSION] = ARTIFACT_SCHEMA_VERSION
    artifact_id: str
    source: str = "simcorrect"
    parameter_patches: list[ParameterPatch] = Field(min_length=1)


class DesignArtifact(BaseModel):
    schema_version: Literal[ARTIFACT_SCHEMA_VERSION] = ARTIFACT_SCHEMA_VERSION
    artifact_id: str
    producer: dict[str, str] = Field(default_factory=lambda: {"name": "opencad", "version": __version__})
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    feature_tree: FeatureTree
    parameters: dict[str, DesignParameter] = Field(default_factory=dict)
    simulation_tags: list[SimulationTag] = Field(default_factory=list)

    @model_validator(mode="after")
    def _parameter_keys_match_names(self) -> Self:
        for name, parameter in self.parameters.items():
            if parameter.name != name:
                raise ValueError(f"Parameter map key '{name}' does not match parameter name '{parameter.name}'.")
        return self

    def parameter_values(self) -> dict[str, ParameterValue]:
        return {name: parameter.value for name, parameter in self.parameters.items()}

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(_to_json(self.model_dump(mode="json")), encoding="utf-8")


def build_design_artifact(
    *,
    artifact_id: str,
    feature_tree: FeatureTree,
    parameters: dict[str, Any] | Iterable[DesignParameter | dict[str, Any]] | None = None,
    simulation_tags: Iterable[SimulationTag | dict[str, Any]] | None = None,
) -> DesignArtifact:
    return DesignArtifact(
        artifact_id=artifact_id,
        feature_tree=feature_tree,
        parameters=_parameter_map(parameters),
        simulation_tags=[SimulationTag.model_validate(tag) for tag in simulation_tags or []],
    )


def export_design_artifact(
    path: str | Path,
    *,
    artifact_id: str,
    context: RuntimeContext | None = None,
    parameters: dict[str, Any] | Iterable[DesignParameter | dict[str, Any]] | None = None,
    simulation_tags: Iterable[SimulationTag | dict[str, Any]] | None = None,
) -> DesignArtifact:
    if context is None:
        from opencad.runtime import get_default_context

        context = get_default_context()
    artifact = build_design_artifact(
        artifact_id=artifact_id,
        feature_tree=context.tree,
        parameters=parameters,
        simulation_tags=simulation_tags,
    )
    artifact.write_json(path)
    return artifact


def load_design_artifact(path: str | Path) -> DesignArtifact:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_design_artifact_payload(payload)
    return DesignArtifact.model_validate(payload)


def apply_design_patch(artifact: DesignArtifact, patch: DesignPatch | dict[str, Any]) -> DesignArtifact:
    if isinstance(patch, dict):
        validate_design_patch_payload(patch)
    patch_model = DesignPatch.model_validate(patch)
    if patch_model.artifact_id != artifact.artifact_id:
        raise ValueError(f"Patch targets '{patch_model.artifact_id}', not '{artifact.artifact_id}'.")

    parameters = dict(artifact.parameters)
    for item in patch_model.parameter_patches:
        if item.name not in parameters:
            raise ValueError(f"Unknown design parameter '{item.name}'.")
        current = parameters[item.name]
        if item.old_value is not None and item.old_value != current.value:
            raise ValueError(
                f"Patch for '{item.name}' expected old value {item.old_value!r}, "
                f"but artifact has {current.value!r}."
            )
        parameters[item.name] = current.model_copy(update={"value": item.value})

    return artifact.model_copy(update={"parameters": parameters})


def validate_design_artifact_payload(payload: Any) -> None:
    _require_object(payload, "CAID design artifact")
    _require_keys(payload, ARTIFACT_REQUIRED_KEYS, "CAID design artifact")
    DesignArtifact.model_validate(payload)


def validate_design_patch_payload(payload: Any) -> None:
    _require_object(payload, "CAID design patch")
    _require_keys(payload, PATCH_REQUIRED_KEYS, "CAID design patch")
    DesignPatch.model_validate(payload)


def _parameter_map(
    parameters: dict[str, Any] | Iterable[DesignParameter | dict[str, Any]] | None,
) -> dict[str, DesignParameter]:
    if parameters is None:
        return {}
    if isinstance(parameters, dict):
        items = []
        for name, value in parameters.items():
            payload = dict(value) if isinstance(value, dict) else {"value": value}
            payload.setdefault("name", name)
            items.append(payload)
    else:
        items = list(parameters)

    mapped: dict[str, DesignParameter] = {}
    for item in items:
        parameter = DesignParameter.model_validate(item)
        mapped[parameter.name] = parameter
    return mapped


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _require_object(payload: Any, label: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object.")


def _require_keys(payload: dict[str, Any], required: frozenset[str], label: str) -> None:
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"{label} missing required key(s): {', '.join(missing)}.")
