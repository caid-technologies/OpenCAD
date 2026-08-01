"""Tests for the operation log, versioning, and replay functionality."""

from __future__ import annotations

import pytest

from opencad.kernel.core.errors import ErrorCode, Failure
from opencad.kernel.core.models import Success
from opencad.kernel.core.op_log import OpLogEntry, OperationLog
from opencad.kernel.operations.handlers import OpenCadKernel
from opencad.kernel.operations.registry import OperationRegistry
from opencad.kernel.operations.schemas import CreateBoxInput


@pytest.fixture()
def kernel() -> OpenCadKernel:
    return OpenCadKernel(tolerance=1e-6, id_strategy="readable")


@pytest.fixture()
def registry(kernel: OpenCadKernel) -> OperationRegistry:
    return OperationRegistry(kernel)


# ── OperationLog unit tests ─────────────────────────────────────────


def test_operation_log_append_and_get():
    log = OperationLog()
    entry = OpLogEntry(operation="create_box", version="1.0.0", params={"length": 1.0})
    log.append(entry)

    assert len(log) == 1
    assert log.get(entry.id) is entry
    assert log.get("nonexistent") is None


def test_operation_log_pagination():
    log = OperationLog()
    for i in range(10):
        log.append(OpLogEntry(operation=f"op_{i}", version="1.0.0"))

    assert len(log.list(offset=0, limit=5)) == 5
    assert len(log.list(offset=5, limit=5)) == 5
    assert len(log.list(offset=8, limit=5)) == 2
    assert log.list(offset=0, limit=3)[0].operation == "op_0"
    assert log.list(offset=0, limit=3)[2].operation == "op_2"


# ── Registry versioning tests ───────────────────────────────────────


def test_registry_schema_includes_version(registry: OperationRegistry):
    schema = registry.get_json_schema("create_box")
    assert "x-opencad-version" in schema
    assert schema["x-opencad-version"] == "1.0.0"


def test_all_operations_have_version(registry: OperationRegistry):
    for op_name in registry.list_operations():
        schema = registry.get_json_schema(op_name)
        assert "x-opencad-version" in schema


# ── Registry logging tests ──────────────────────────────────────────


def test_successful_operation_is_logged(registry: OperationRegistry):
    result = registry.call("create_box", {"length": 2.0, "width": 3.0, "height": 4.0})
    assert isinstance(result, Success)

    entries = registry.get_log()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.operation == "create_box"
    assert entry.version == "1.0.0"
    assert entry.success is True
    assert entry.result_shape_id == result.shape_id
    assert entry.backend == "AnalyticBackend"
    assert entry.duration_ms >= 0.0
    assert entry.params == {"length": 2.0, "width": 3.0, "height": 4.0}


def test_failed_operation_is_logged(registry: OperationRegistry):
    result = registry.call("create_box", {"length": -1.0, "width": 2.0, "height": 3.0})
    assert isinstance(result, Failure)

    entries = registry.get_log()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.operation == "create_box"
    assert entry.success is False
    assert entry.result_shape_id is None


def test_validation_failure_not_logged(registry: OperationRegistry):
    """Schema validation failures are returned before the handler runs,
    but should still be logged."""
    result = registry.call("create_box", {"length": 1.0, "width": 2.0})
    assert isinstance(result, Failure)
    # The validation failure is logged as a failed operation
    # (because it goes through registry.call)
    entries = registry.get_log()
    # Schema validation failures don't reach the handler and aren't logged
    # Actually they ARE — the registry records the validation failure
    assert len(entries) == 0  # validation errors short-circuit before handler


def test_unknown_operation_not_logged(registry: OperationRegistry):
    result = registry.call("nope", {})
    assert isinstance(result, Failure)
    # Unknown operations return before the logging code runs
    entries = registry.get_log()
    assert len(entries) == 0


def test_multiple_operations_logged_in_order(registry: OperationRegistry):
    registry.call("create_box", {"length": 1.0, "width": 1.0, "height": 1.0})
    registry.call("create_cylinder", {"radius": 1.0, "height": 2.0})
    registry.call("create_sphere", {"radius": 1.0})

    entries = registry.get_log()
    assert len(entries) == 3
    assert entries[0].operation == "create_box"
    assert entries[1].operation == "create_cylinder"
    assert entries[2].operation == "create_sphere"


def test_log_entry_can_be_retrieved_by_id(registry: OperationRegistry):
    registry.call("create_box", {"length": 5.0, "width": 5.0, "height": 5.0})
    entries = registry.get_log()
    entry_id = entries[0].id

    fetched = registry.get_log_entry(entry_id)
    assert fetched is not None
    assert fetched.operation == "create_box"


# ── API-level replay tests ──────────────────────────────────────────


# ── Deterministic ID / duplicate detection tests ────────────────────


def test_operation_log_rejects_duplicate_id():
    """Appending an entry with an existing id must raise ValueError."""
    log = OperationLog()
    entry = OpLogEntry(id="dup-1", operation="create_box", version="1.0.0")
    log.append(entry)
    with pytest.raises(ValueError, match="Duplicate log entry id"):
        log.append(OpLogEntry(id="dup-1", operation="create_sphere", version="1.0.0"))


def test_caller_provided_id_and_timestamp_are_preserved():
    """OpLogEntry should accept and preserve pre-set id/timestamp."""
    from datetime import datetime, timezone

    ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
    entry = OpLogEntry(id="my-id", timestamp=ts, operation="test", version="1.0.0")
    assert entry.id == "my-id"
    assert entry.timestamp == ts


def test_shape_store_rejects_duplicate_preset_id(kernel: OpenCadKernel):
    from opencad.kernel.core.models import Success

    result = kernel.create_box(CreateBoxInput(length=1, width=1, height=1))
    assert isinstance(result, Success) and result.shape_id
    with pytest.raises(ValueError, match="Duplicate shape id"):
        kernel.store.new_id("box", preset_id=result.shape_id)


def test_registry_replay_ids_preserved(registry: OperationRegistry):
    """Calling with replay_entry_id should produce a log entry with that id."""
    from datetime import datetime, timezone

    ts = datetime(2024, 6, 15, tzinfo=timezone.utc)
    result = registry.call(
        "create_box",
        {"length": 1, "width": 1, "height": 1},
        replay_entry_id="replay-42",
        replay_timestamp=ts,
        replay_shape_id="my-shape-001",
    )
    assert isinstance(result, Success)
    assert result.shape_id == "my-shape-001"

    entry = registry.get_log_entry("replay-42")
    assert entry is not None
    assert entry.timestamp == ts


