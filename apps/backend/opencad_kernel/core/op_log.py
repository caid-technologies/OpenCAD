"""Append-only operation log for the kernel.

Every operation call is recorded with its name, version, validated
parameters, result, and wall-clock duration.  The log is JSON-
serializable and can be replayed against any kernel backend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class OpLogEntry(BaseModel):
    """Single entry in the operation log.

    ``id`` and ``timestamp`` default to fresh values but callers may supply
    pre-set values for deterministic replay.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operation: str
    version: str
    backend: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    result_shape_id: str | None = None
    success: bool = True
    duration_ms: float = 0.0


class OperationLog:
    """In-memory, append-only operation journal."""

    def __init__(self) -> None:
        self._entries: list[OpLogEntry] = []
        self._index: dict[str, OpLogEntry] = {}

    def append(self, entry: OpLogEntry) -> OpLogEntry:
        if entry.id in self._index:
            raise ValueError(f"Duplicate log entry id '{entry.id}'.")
        self._entries.append(entry)
        self._index[entry.id] = entry
        return entry

    def get(self, entry_id: str) -> OpLogEntry | None:
        return self._index.get(entry_id)

    def list(self, *, offset: int = 0, limit: int = 100) -> list[OpLogEntry]:
        return self._entries[offset : offset + limit]

    def __len__(self) -> int:
        return len(self._entries)
