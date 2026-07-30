from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

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
    parent_id: str | None = None                                    # NEW
    tool_refs: list[str] = Field(default_factory=list)              # NEW
    shape_id: str | None = None
    status: NodeStatus = "pending"
    suppressed: bool = False
    mate_id: str | None = None
    is_assembly_mate: bool = False

    @computed_field  # type: ignore[misc]
    @property
    def depends_on(self) -> list[str]:
        """Back-compat: derived from parent_id + tool_refs."""
        if self.parent_id is None:
            return list(self.tool_refs)
        return [self.parent_id, *self.tool_refs]


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
