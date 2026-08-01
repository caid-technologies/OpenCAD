"""Versioned snapshot schema for deterministic persistence and replay.

A snapshot captures the complete kernel state — every operation log entry
with its original identity, plus the resulting shape ID inventory — in a
format that can be replayed on any backend to reproduce the exact same
state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from opencad_kernel.core.op_log import OpLogEntry

SNAPSHOT_VERSION = 1


class SnapshotV1(BaseModel):
    """Immutable, versioned capture of kernel state."""

    version: int = Field(default=SNAPSHOT_VERSION, frozen=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entries: list[OpLogEntry] = Field(default_factory=list)
    shape_ids: list[str] = Field(default_factory=list)
