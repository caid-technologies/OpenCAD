from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Type

from pydantic import BaseModel
from pydantic import ValidationError

from opencad_kernel.core.errors import ErrorCode, make_failure
from opencad_kernel.core.models import OperationResult, Success
from opencad_kernel.core.op_log import OpLogEntry, OperationLog
from opencad_kernel.operations.handlers import OpenCadKernel
from opencad_kernel.operations.schemas import (
    BooleanInput,
    ChamferEdgesInput,
    CircularPatternInput,
    CreateAssemblyMateInput,
    CreateBoxInput,
    CreateConeInput,
    CreateCylinderInput,
    CreateSketchInput,
    CreateSphereInput,
    CreateTorusInput,
    DeleteAssemblyMateInput,
    DraftInput,
    ExportStlInput,
    ExportStepInput,
    ExtrudeInput,
    FilletEdgesInput,
    ImportStepInput,
    ImportStlInput,
    LinearPatternInput,
    ListAssemblyMatesInput,
    LoftInput,
    MirrorInput,
    OffsetShapeInput,
    RevolveInput,
    ShellInput,
    SweepInput,
)


@dataclass
class OperationSpec:
    name: str
    version: str
    input_model: Type[BaseModel]
    handler: Callable[[BaseModel], OperationResult]


class OperationRegistry:
    def __init__(self, kernel: OpenCadKernel) -> None:
        self.kernel = kernel
        self._ops: dict[str, OperationSpec] = {}
        self._log = OperationLog()
        self._register_defaults()

    def _register(
        self,
        name: str,
        input_model: Type[BaseModel],
        handler: Callable[[BaseModel], OperationResult],
        *,
        version: str = "1.0.0",
    ) -> None:
        self._ops[name] = OperationSpec(name=name, version=version, input_model=input_model, handler=handler)

    def _register_defaults(self) -> None:
        # Primitives
        self._register("create_box", CreateBoxInput, self.kernel.create_box)
        self._register("create_cylinder", CreateCylinderInput, self.kernel.create_cylinder)
        self._register("create_sphere", CreateSphereInput, self.kernel.create_sphere)
        self._register("create_cone", CreateConeInput, self.kernel.create_cone)
        self._register("create_torus", CreateTorusInput, self.kernel.create_torus)
        # Booleans
        self._register("boolean_union", BooleanInput, self.kernel.boolean_union)
        self._register("boolean_cut", BooleanInput, self.kernel.boolean_cut)
        self._register("boolean_intersection", BooleanInput, self.kernel.boolean_intersection)
        # Edge / face operations
        self._register("fillet_edges", FilletEdgesInput, self.kernel.fillet_edges)
        self._register("chamfer_edges", ChamferEdgesInput, self.kernel.chamfer_edges)
        self._register("shell", ShellInput, self.kernel.shell)
        self._register("draft", DraftInput, self.kernel.draft)
        self._register("offset_shape", OffsetShapeInput, self.kernel.offset_shape)
        # Sketch operations
        self._register("create_sketch", CreateSketchInput, self.kernel.create_sketch)
        self._register("extrude", ExtrudeInput, self.kernel.extrude)
        # Sweep / loft / revolve
        self._register("revolve", RevolveInput, self.kernel.revolve)
        self._register("sweep", SweepInput, self.kernel.sweep)
        self._register("loft", LoftInput, self.kernel.loft)
        # Patterns
        self._register("linear_pattern", LinearPatternInput, self.kernel.linear_pattern)
        self._register("circular_pattern", CircularPatternInput, self.kernel.circular_pattern)
        self._register("mirror", MirrorInput, self.kernel.mirror)
        # CAD file I/O
        self._register("import_step", ImportStepInput, self.kernel.import_step)
        self._register("export_step", ExportStepInput, self.kernel.export_step)
        self._register("import_stl", ImportStlInput, self.kernel.import_stl)
        self._register("export_stl", ExportStlInput, self.kernel.export_stl)
        # Assembly mates (3-D constraints — Phase 1)
        self._register("create_assembly_mate", CreateAssemblyMateInput, self.kernel.create_assembly_mate)
        self._register("delete_assembly_mate", DeleteAssemblyMateInput, self.kernel.delete_assembly_mate)
        self._register("list_assembly_mates", ListAssemblyMatesInput, self.kernel.list_assembly_mates)

    def list_operations(self) -> list[str]:
        return list(self._ops.keys())

    def get_json_schema(self, name: str) -> dict:
        if name not in self._ops:
            raise ValueError(f"Unknown operation '{name}'.")
        spec = self._ops[name]
        schema = spec.input_model.model_json_schema()
        schema["x-opencad-version"] = spec.version
        return schema

    def call(
        self,
        name: str,
        payload: dict,
        *,
        replay_entry_id: str | None = None,
        replay_timestamp: datetime | None = None,
        replay_shape_id: str | None = None,
    ) -> OperationResult:
        """Execute an operation.

        During replay the caller may supply ``replay_entry_id``,
        ``replay_timestamp``, and ``replay_shape_id`` so that the resulting
        log entry and shape keep their original identities.
        """
        if name not in self._ops:
            return make_failure(
                code=ErrorCode.INVALID_INPUT,
                message=f"Unknown operation '{name}'.",
                suggestion=f"Use one of: {', '.join(self.list_operations())}.",
                failed_check="operation_lookup",
            )

        spec = self._ops[name]
        try:
            parsed = spec.input_model.model_validate(payload)
        except ValidationError as exc:
            return make_failure(
                code=ErrorCode.INVALID_INPUT,
                message=f"Invalid payload for '{name}': {exc.errors()}",
                suggestion="Provide all required fields with valid values per schema.",
                failed_check="schema_validation",
            )

        # Inject preset shape ID for deterministic replay.
        if replay_shape_id is not None:
            self.kernel.store._next_preset_id = replay_shape_id

        start = time.perf_counter()
        result = spec.handler(parsed)
        duration_ms = (time.perf_counter() - start) * 1000.0

        # Clear any unconsumed preset.
        self.kernel.store._next_preset_id = None

        # Log the operation
        is_success = isinstance(result, Success)
        entry_kwargs: dict[str, Any] = {
            "operation": name,
            "version": spec.version,
            "backend": type(self.kernel.backend).__name__,
            "params": payload,
            "result_shape_id": result.shape_id if is_success else None,
            "success": is_success,
            "duration_ms": round(duration_ms, 3),
        }
        if replay_entry_id is not None:
            entry_kwargs["id"] = replay_entry_id
        if replay_timestamp is not None:
            entry_kwargs["timestamp"] = replay_timestamp
        entry = OpLogEntry(**entry_kwargs)
        self._log.append(entry)

        return result

    # ── Log access ──────────────────────────────────────────────────

    def get_log(self, *, offset: int = 0, limit: int = 100) -> list[OpLogEntry]:
        return self._log.list(offset=offset, limit=limit)

    def get_log_entry(self, entry_id: str) -> OpLogEntry | None:
        return self._log.get(entry_id)

    @property
    def log(self) -> OperationLog:
        return self._log
