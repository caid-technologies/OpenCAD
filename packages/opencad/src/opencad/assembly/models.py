from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from opencad.kernel.core.models import RigidTransform


class AssemblyComponent(BaseModel):
    """A stable semantic component in an OpenCAD assembly hierarchy.

    Component identity is intentionally independent from geometry identity.
    Geometry may be regenerated while the component keeps the same id.
    """

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    child_ids: list[str] = Field(default_factory=list)
    geometry_refs: list[str] = Field(default_factory=list)
    feature_refs: list[str] = Field(default_factory=list)
    transform: RigidTransform = Field(default_factory=RigidTransform.identity)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "AssemblyComponent":
        """Reject duplicate local references before tree-level validation."""
        if len(self.child_ids) != len(set(self.child_ids)):
            raise ValueError(f"Assembly component '{self.id}' has duplicate child IDs.")
        if len(self.geometry_refs) != len(set(self.geometry_refs)):
            raise ValueError(f"Assembly component '{self.id}' has duplicate geometry references.")
        if len(self.feature_refs) != len(set(self.feature_refs)):
            raise ValueError(f"Assembly component '{self.id}' has duplicate feature references.")
        return self


class AssemblyTree(BaseModel):
    """Semantic product/component hierarchy independent from feature history."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    root_ids: list[str] = Field(default_factory=list)
    components: dict[str, AssemblyComponent] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> "AssemblyTree":
        """Validate identity, parentage, reachability, and acyclic nesting."""
        if len(self.root_ids) != len(set(self.root_ids)):
            raise ValueError("Assembly tree contains duplicate root IDs.")

        for key, component in self.components.items():
            if key != component.id:
                raise ValueError(
                    f"Assembly component map key '{key}' does not match component ID '{component.id}'."
                )

        for root_id in self.root_ids:
            if root_id not in self.components:
                raise ValueError(f"Assembly root '{root_id}' does not exist.")

        parent_by_child: dict[str, str] = {}
        for component in self.components.values():
            for child_id in component.child_ids:
                if child_id not in self.components:
                    raise ValueError(
                        f"Assembly component '{component.id}' references missing child '{child_id}'."
                    )
                if child_id == component.id:
                    raise ValueError(f"Assembly component '{component.id}' cannot contain itself.")
                existing_parent = parent_by_child.get(child_id)
                if existing_parent is not None and existing_parent != component.id:
                    raise ValueError(
                        f"Assembly component '{child_id}' has multiple parents: "
                        f"'{existing_parent}' and '{component.id}'."
                    )
                parent_by_child[child_id] = component.id

        state: dict[str, int] = {}

        def visit(component_id: str) -> None:
            status = state.get(component_id, 0)
            if status == 1:
                raise ValueError(f"Assembly hierarchy contains a cycle at '{component_id}'.")
            if status == 2:
                return
            state[component_id] = 1
            for child_id in self.components[component_id].child_ids:
                visit(child_id)
            state[component_id] = 2

        for component_id in self.components:
            visit(component_id)

        expected_roots = set(self.components) - set(parent_by_child)
        actual_roots = set(self.root_ids)
        if actual_roots != expected_roots:
            missing = sorted(expected_roots - actual_roots)
            extra = sorted(actual_roots - expected_roots)
            details: list[str] = []
            if missing:
                details.append(f"missing roots={missing}")
            if extra:
                details.append(f"non-root entries={extra}")
            raise ValueError("Assembly root IDs do not match hierarchy: " + ", ".join(details))

        return self

    def descendant_ids(self, component_id: str, *, include_self: bool = True) -> list[str]:
        """Return a component and/or descendants in deterministic depth-first order."""
        if component_id not in self.components:
            raise KeyError(f"Assembly component '{component_id}' does not exist.")

        ordered: list[str] = []

        def walk(current_id: str) -> None:
            ordered.append(current_id)
            for child_id in self.components[current_id].child_ids:
                walk(child_id)

        walk(component_id)
        return ordered if include_self else ordered[1:]

    def geometry_refs_for(
        self,
        component_id: str,
        *,
        include_descendants: bool = True,
    ) -> list[str]:
        """Resolve geometry references for a semantic component selection."""
        component_ids = (
            self.descendant_ids(component_id)
            if include_descendants
            else [component_id]
        )
        geometry_refs: list[str] = []
        seen: set[str] = set()
        for current_id in component_ids:
            for geometry_ref in self.components[current_id].geometry_refs:
                if geometry_ref not in seen:
                    seen.add(geometry_ref)
                    geometry_refs.append(geometry_ref)
        return geometry_refs

    def replace_component_geometry(
        self,
        component_id: str,
        geometry_refs: list[str],
    ) -> "AssemblyTree":
        """Return a copy with regenerated geometry while preserving component identity."""
        if component_id not in self.components:
            raise KeyError(f"Assembly component '{component_id}' does not exist.")

        updated = self.model_copy(deep=True)
        updated.components[component_id].geometry_refs = list(geometry_refs)
        return AssemblyTree.model_validate(updated.model_dump())


ASSEMBLY_SNAPSHOT_VERSION = 1


class AssemblySnapshotV1(BaseModel):
    """Versioned persistence envelope for an OpenCAD assembly hierarchy."""

    version: int = Field(default=ASSEMBLY_SNAPSHOT_VERSION, frozen=True)
    assembly: AssemblyTree
