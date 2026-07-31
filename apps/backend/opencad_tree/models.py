from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

NodeStatus = Literal["pending", "built", "failed", "stale", "suppressed"]
ParameterType = Literal["int", "float", "bool", "string", "shape_ref", "json"]


class TypedParameter(BaseModel):
    type: ParameterType
    value: Any = None


class ParameterBinding(BaseModel):
    parameter: str
    source: Literal["solver", "node"]
    source_key: str
    source_path: str
    cast_as: ParameterType | None = None
    expression: str | None = None


class FeatureNode(BaseModel):
    id: str
    name: str
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    typed_parameters: dict[str, TypedParameter] = Field(default_factory=dict)
    parameter_bindings: list[ParameterBinding] = Field(default_factory=list)
    sketch_id: str | None = None
    parent_id: str | None = None
    tool_refs: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    shape_id: str | None = None
    status: NodeStatus = "pending"
    suppressed: bool = False
    mate_id: str | None = None
    is_assembly_mate: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_dependencies(cls, value: Any) -> Any:
        """Keep rebuild dependencies distinct from visual body lineage.

        ``sketch_id`` is a profile dependency for consuming features, never a
        body parent. Legacy ``depends_on`` payloads are still translated into
        the newer parent/tool roles.
        """
        if not isinstance(value, dict):
            return value

        data = dict(value)
        operation = str(data.get("operation", ""))
        node_id = data.get("id")
        sketch_id = data.get("sketch_id")
        owns_sketch = operation in {"sketch", "add_sketch", "create_sketch"} or sketch_id == node_id
        profile_ref = sketch_id if isinstance(sketch_id, str) and not owns_sketch else None

        dependencies = list(dict.fromkeys(data.get("depends_on") or []))
        parent_id = data.get("parent_id")
        tool_refs = list(data.get("tool_refs") or [])

        # Migrate the old extrusion shape where the profile was incorrectly
        # stored as the body's lineage parent/tool.
        if profile_ref is not None:
            if parent_id == profile_ref:
                parent_id = None
            tool_refs = [ref for ref in tool_refs if ref != profile_ref]

        has_explicit_roles = "parent_id" in data or "tool_refs" in data
        if not has_explicit_roles and dependencies:
            lineage_dependencies = [ref for ref in dependencies if ref != profile_ref]
            parent_id = lineage_dependencies[0] if lineage_dependencies else None
            tool_refs = lineage_dependencies[1:]

        normalized_dependencies = [
            ref
            for ref in [parent_id, *tool_refs, profile_ref]
            if isinstance(ref, str) and ref
        ]
        # Preserve dependencies that do not yet have a richer role so old
        # graph payloads and direct dependency editing remain compatible.
        normalized_dependencies.extend(
            ref for ref in dependencies if ref not in normalized_dependencies
        )

        data["parent_id"] = parent_id
        data["tool_refs"] = list(dict.fromkeys(tool_refs))
        data["depends_on"] = list(dict.fromkeys(normalized_dependencies))
        return data


class FeatureTree(BaseModel):
    nodes: dict[str, FeatureNode] = Field(default_factory=dict)
    root_id: str
    active_branch: str = "main"
    branch_snapshots: dict[str, dict[str, FeatureNode]] = Field(default_factory=dict)
    solver_cache: dict[str, dict[str, Any]] = Field(default_factory=dict)
    revision: int = 0


class RebuildRequest(BaseModel):
    continue_on_error: bool = False


TREE_SNAPSHOT_VERSION = 1


class TreeSnapshotV1(BaseModel):
    """Versioned snapshot of a feature tree for persistence / restore."""

    version: int = Field(default=TREE_SNAPSHOT_VERSION, frozen=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tree: FeatureTree
