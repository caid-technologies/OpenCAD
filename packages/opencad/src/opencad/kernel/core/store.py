from __future__ import annotations

from collections import defaultdict
from typing import Literal
from uuid import uuid4

from .models import AssemblyMate, ShapeData

IdStrategy = Literal["uuid", "readable"]


class ShapeStore:
    def __init__(self, id_strategy: IdStrategy = "uuid") -> None:
        self._id_strategy = id_strategy
        self._shapes: dict[str, ShapeData] = {}
        self._counters: defaultdict[str, int] = defaultdict(int)
        # Set by OperationRegistry during replay so the next new_id() call
        # returns the stored identity instead of generating a fresh one.
        self._next_preset_id: str | None = None

    def new_id(self, kind: str, *, preset_id: str | None = None) -> str:
        """Generate or accept a shape identifier.

        When *preset_id* is given (e.g. during replay) it is returned as-is
        after checking for duplicates in the store.  A queued
        ``_next_preset_id`` from the registry is also consumed here.
        """
        effective = preset_id or self._next_preset_id
        self._next_preset_id = None
        if effective is not None:
            if effective in self._shapes:
                raise ValueError(f"Duplicate shape id '{effective}'.")
            return effective
        if self._id_strategy == "uuid":
            return str(uuid4())
        self._counters[kind] += 1
        return f"{kind}-{self._counters[kind]:04d}"

    def add(self, shape: ShapeData) -> ShapeData:
        self._shapes[shape.id] = shape
        return shape

    def get(self, shape_id: str) -> ShapeData | None:
        return self._shapes.get(shape_id)

    def all_ids(self) -> list[str]:
        return list(self._shapes.keys())

    def set_manifold(self, shape_id: str, manifold: bool) -> None:
        shape = self._shapes[shape_id]
        shape.manifold = manifold
        self._shapes[shape_id] = shape


class MateStore:
    """In-memory store for assembly mate constraints."""

    def __init__(self, id_strategy: IdStrategy = "uuid") -> None:
        self._id_strategy = id_strategy
        self._mates: dict[str, AssemblyMate] = {}
        self._counter: int = 0

    def new_id(self) -> str:
        if self._id_strategy == "uuid":
            return str(uuid4())
        self._counter += 1
        return f"mate-{self._counter:04d}"

    def add(self, mate: AssemblyMate) -> AssemblyMate:
        self._mates[mate.id] = mate
        return mate

    def get(self, mate_id: str) -> AssemblyMate | None:
        return self._mates.get(mate_id)

    def delete(self, mate_id: str) -> bool:
        return self._mates.pop(mate_id, None) is not None

    def by_entity(self, entity_ref: str) -> list[AssemblyMate]:
        """Return all mates involving a given entity reference."""
        return [
            m for m in self._mates.values()
            if m.entity_a == entity_ref or m.entity_b == entity_ref
        ]

    def all(self) -> list[AssemblyMate]:
        return list(self._mates.values())

    def all_ids(self) -> list[str]:
        return list(self._mates.keys())
