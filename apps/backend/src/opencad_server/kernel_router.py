from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from opencad.version import __version__
from opencad.kernel.core.backend_factory import create_backend
from opencad.kernel.core.errors import Failure
from opencad.kernel.core.backend import StreamingMeshBackend
from opencad.kernel.core.models import MeshData, OperationResult, Success
from opencad.kernel.core.snapshot import SnapshotV1
from opencad.kernel.operations.handlers import OpenCadKernel
from opencad.kernel.operations.registry import OperationRegistry
from opencad.kernel.operations.schemas import SelectorQuery
from opencad_server.api_app import create_api_app

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

# ── Backend selection ───────────────────────────────────────────────

_BACKEND_NAME = os.environ.get("OPENCAD_KERNEL_BACKEND", "occt")


def _build_kernel() -> OpenCadKernel:
    backend = create_backend(_BACKEND_NAME)
    logger.info("Kernel started with %s backend", type(backend).__name__)
    return OpenCadKernel(backend=backend)


_KERNEL = _build_kernel()
_REGISTRY = OperationRegistry(_KERNEL)


class OperationCallRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class CadImportResponse(BaseModel):
    shape_id: str
    filename: str
    format: Literal["step", "stp", "stl"]


_CAD_MEDIA_TYPES = {
    "step": "model/step",
    "stp": "model/step",
    "stl": "model/stl",
}
_MAX_CAD_UPLOAD_BYTES = 100 * 1024 * 1024


# ── Health ──────────────────────────────────────────────────────────


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "backend": _BACKEND_NAME}


@router.post("/files/import", response_model=CadImportResponse)
async def import_cad_file(request: Request, filename: str = Query(min_length=1)) -> CadImportResponse:
    safe_filename = Path(filename).name
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in {".step", ".stp", ".stl"}:
        raise HTTPException(status_code=415, detail="Supported import formats are .step, .stp, and .stl.")

    file_descriptor, temporary_path = tempfile.mkstemp(suffix=suffix)
    os.close(file_descriptor)
    total_bytes = 0
    try:
        with open(temporary_path, "wb") as output:
            async for chunk in request.stream():
                total_bytes += len(chunk)
                if total_bytes > _MAX_CAD_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="CAD uploads are limited to 100 MB.")
                output.write(chunk)
        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded CAD file is empty.")

        operation = "import_stl" if suffix == ".stl" else "import_step"
        result = _REGISTRY.call(operation, {"filepath": temporary_path})
        if isinstance(result, Failure):
            raise HTTPException(status_code=422, detail=result.message)
        if not result.shape_id:
            raise HTTPException(status_code=500, detail="CAD import returned no shape ID.")
        return CadImportResponse(
            shape_id=result.shape_id,
            filename=safe_filename,
            format=suffix.removeprefix("."),
        )
    finally:
        Path(temporary_path).unlink(missing_ok=True)


@router.get("/files/{shape_id}/export")
def export_cad_file(
    shape_id: str,
    format: Literal["step", "stp", "stl"] = Query(),
    filename: str | None = Query(default=None),
) -> FileResponse:
    suffix = f".{format}"
    file_descriptor, temporary_path = tempfile.mkstemp(suffix=suffix)
    os.close(file_descriptor)
    operation = "export_stl" if format == "stl" else "export_step"
    result = _REGISTRY.call(operation, {"shape_id": shape_id, "filepath": temporary_path})
    if isinstance(result, Failure):
        Path(temporary_path).unlink(missing_ok=True)
        status_code = 404 if result.code.value == "SHAPE_NOT_FOUND" else 422
        raise HTTPException(status_code=status_code, detail=result.message)

    requested_name = Path(filename).name if filename else f"opencad-{shape_id}{suffix}"
    if Path(requested_name).suffix.lower() != suffix:
        requested_name = f"{Path(requested_name).stem}{suffix}"
    return FileResponse(
        temporary_path,
        media_type=_CAD_MEDIA_TYPES[format],
        filename=requested_name,
        background=BackgroundTask(Path(temporary_path).unlink, missing_ok=True),
    )


# ── Operations ──────────────────────────────────────────────────────


@router.get("/operations", response_model=list[str])
def list_operations() -> list[str]:
    return _REGISTRY.list_operations()


# ── Operation log (must be before /operations/{name} to avoid capture) ──


@router.get("/operations/log")
def get_operation_log(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    entries = _REGISTRY.get_log(offset=offset, limit=limit)
    return [e.model_dump() for e in entries]


@router.get("/operations/log/{entry_id}")
def get_log_entry(entry_id: str) -> dict[str, Any]:
    entry = _REGISTRY.get_log_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Log entry '{entry_id}' not found.")
    return entry.model_dump()


# ── Snapshot ────────────────────────────────────────────────────────


@router.get("/snapshot", response_model=SnapshotV1)
def get_snapshot() -> SnapshotV1:
    """Return a versioned snapshot of the current kernel state."""
    return SnapshotV1(
        entries=_REGISTRY.get_log(offset=0, limit=len(_REGISTRY.log)),
        shape_ids=_KERNEL.store.all_ids(),
    )


# ── Replay (must be before /operations/{name} to avoid capture) ─────


class ReplayRequest(BaseModel):
    entries: list[dict[str, Any]]


@router.post("/operations/replay")
def replay_operations(request: ReplayRequest) -> dict[str, Any]:
    """Replay operation log entries against a fresh kernel.

    Each entry may carry ``id``, ``timestamp``, and ``result_shape_id``
    fields.  When present they are forwarded to the registry so the
    replayed state is identity-identical to the original.
    """
    fresh_kernel = _build_kernel()
    fresh_registry = OperationRegistry(fresh_kernel)
    results: list[dict[str, Any]] = []

    for entry in request.entries:
        op_name = entry.get("operation", "")
        params = entry.get("params", {})
        result = fresh_registry.call(
            op_name,
            params,
            replay_entry_id=entry.get("id"),
            replay_timestamp=entry.get("timestamp"),
            replay_shape_id=entry.get("result_shape_id"),
        )
        if isinstance(result, Success):
            results.append({"ok": True, "shape_id": result.shape_id, "operation": op_name})
        else:
            results.append({"ok": False, "code": result.code, "message": result.message, "operation": op_name})

    return {
        "replayed": len(results),
        "results": results,
        "shape_ids": fresh_kernel.store.all_ids(),
    }


# ── Operation call (wildcard — must come after specific routes) ─────


@router.get("/operations/{name}/schema")
def get_operation_schema(name: str) -> dict[str, Any]:
    try:
        return _REGISTRY.get_json_schema(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/operations/{name}", response_model=Success | Failure)
def call_operation(name: str, request: OperationCallRequest) -> OperationResult:
    return _REGISTRY.call(name, request.payload)


# ── Topology endpoints ──────────────────────────────────────────────


@router.get("/shapes/{shape_id}/topology")
def get_topology(shape_id: str) -> dict[str, Any]:
    """Return the full topology map (faces + edges with stable refs)."""
    try:
        topo = _KERNEL.get_topology(shape_id)
        return topo.model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/shapes/{shape_id}/faces")
def get_faces(shape_id: str) -> list[dict[str, Any]]:
    """List all face refs for a shape."""
    try:
        topo = _KERNEL.get_topology(shape_id)
        return [f.model_dump() for f in topo.faces]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/shapes/{shape_id}/edges")
def get_edges(shape_id: str) -> list[dict[str, Any]]:
    """List all edge refs for a shape."""
    try:
        topo = _KERNEL.get_topology(shape_id)
        return [e.model_dump() for e in topo.edges]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/shapes/{shape_id}/select")
def select_subshapes(shape_id: str, query: SelectorQuery) -> list[dict[str, Any]]:
    """Run a selector query against the shape's topology."""
    try:
        results = _KERNEL.select_subshapes(shape_id, query)
        return [r.model_dump() for r in results]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Mesh endpoints ──────────────────────────────────────────────────


@router.get("/shapes/{shape_id}/mesh", response_model=MeshData)
def get_mesh(
    shape_id: str,
    deflection: float = Query(default=0.1, gt=0.0),
) -> MeshData:
    try:
        return _KERNEL.tessellate(shape_id, deflection)
    except NotImplementedError as exc:
        logger.info("Mesh tessellation is unavailable: %s", exc)
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/shapes/{shape_id}/mesh/stream")
async def stream_mesh(
    shape_id: str,
    deflection: float = Query(default=0.1, gt=0.0),
) -> StreamingResponse:
    """Stream tessellated mesh face-by-face as Server-Sent Events."""
    backend = _KERNEL.backend
    if not isinstance(backend, StreamingMeshBackend):
        raise HTTPException(
            status_code=501,
            detail="Streaming tessellation requires a face-streaming backend.",
        )

    # Verify shape exists before starting the stream
    if backend.store.get(shape_id) is None:
        raise HTTPException(status_code=404, detail=f"Shape '{shape_id}' not found.")

    async def _event_generator():
        try:
            total = backend.count_faces(shape_id)
            for face_idx in range(total):
                mesh, _ = backend.tessellate_face(shape_id, face_idx, deflection)
                chunk = {
                    "vertices": mesh.vertices,
                    "faces": mesh.faces,
                    "normals": mesh.normals,
                    "face_groups": [group.model_dump() for group in mesh.face_groups],
                    "faceIndex": face_idx,
                    "totalFaces": total,
                    "done": face_idx == total - 1,
                }
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def create_app() -> FastAPI:
    """Build a standalone kernel service app."""
    standalone = create_api_app(title="OpenCAD Kernel", version=__version__)
    standalone.include_router(router)
    return standalone


app: FastAPI = create_app()
