from __future__ import annotations

import json
from typing import Any, Mapping

from pydantic import ValidationError

from opencad.assembly.models import ASSEMBLY_SNAPSHOT_VERSION, AssemblySnapshotV1, AssemblyTree


def serialize_assembly_tree(tree: AssemblyTree) -> str:
    """Serialize an assembly tree using the versioned OpenCAD envelope."""
    return AssemblySnapshotV1(assembly=tree).model_dump_json()


def deserialize_assembly_tree(payload: str) -> AssemblyTree:
    """Deserialize and validate a versioned OpenCAD assembly payload."""
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid assembly JSON payload.") from exc

    version = raw.get("version") if isinstance(raw, dict) else None
    if version != ASSEMBLY_SNAPSHOT_VERSION:
        raise ValueError(
            f"Unsupported assembly snapshot version {version!r}; "
            f"expected {ASSEMBLY_SNAPSHOT_VERSION}."
        )

    try:
        return AssemblySnapshotV1.model_validate(raw).assembly
    except ValidationError as exc:
        raise ValueError("Invalid assembly snapshot payload.") from exc


def import_assembly_tree(payload: AssemblyTree | Mapping[str, Any] | str) -> AssemblyTree:
    """Normalize an upstream hierarchy into OpenCAD's canonical assembly object.

    Forma and other producers can target this boundary without coupling OpenCAD
    to their source-specific schemas. Strings may be either a versioned
    AssemblySnapshotV1 payload or a raw AssemblyTree JSON object.
    """
    if isinstance(payload, AssemblyTree):
        return payload.model_copy(deep=True)

    if isinstance(payload, str):
        try:
            raw: Any = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid assembly JSON payload.") from exc
        if isinstance(raw, dict) and "version" in raw and "assembly" in raw:
            return deserialize_assembly_tree(payload)
        payload = raw

    try:
        return AssemblyTree.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("Invalid assembly tree payload.") from exc
