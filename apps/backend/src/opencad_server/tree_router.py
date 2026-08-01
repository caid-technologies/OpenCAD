from __future__ import annotations

import hashlib
import math

from dotenv import load_dotenv

load_dotenv()
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from opencad.kernel_adapter import normalize_feature_operation, resolve_feature_references
from opencad.version import __version__
from opencad.kernel.client import KernelClient
from opencad.solver.models import Sketch
from opencad.tree.models import FeatureNode, FeatureTree, RebuildRequest, TreeSnapshotV1
from opencad.tree.service import FeatureTreeService
from opencad_server.api_app import create_api_app
from opencad_server.http_kernel_client import HttpKernelClient

logger = logging.getLogger(__name__)

router = APIRouter()

_TREES: dict[str, FeatureTree] = {}

_USE_LIVE_KERNEL = os.environ.get("OPENCAD_TREE_LIVE_KERNEL", "false").lower() == "true"
_KERNEL_CLIENT: KernelClient | None = HttpKernelClient() if _USE_LIVE_KERNEL else None


class EditFeatureRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


class DeserializeRequest(BaseModel):
    payload: str


class SuppressFeatureRequest(BaseModel):
    suppressed: bool = True


class TypedParameterRequest(BaseModel):
    typed_parameters: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BranchCreateRequest(BaseModel):
    branch_name: str
    from_branch: str | None = None


class SolverUpdateRequest(BaseModel):
    solved_sketch: dict[str, Any]


def _get_tree_or_404(tree_id: str) -> FeatureTree:
    tree = _TREES.get(tree_id)
    if not tree:
        raise HTTPException(status_code=404, detail=f"Tree '{tree_id}' not found.")
    return tree


def _kernel_client(node: FeatureNode, _tree: FeatureTree) -> str:
    """Execute a feature node against the configured kernel.

    Falls back to a deterministic hash stub when no kernel client is
    configured (the default) so that tests and mock mode continue to work.
    """
    if _KERNEL_CLIENT is None:
        return _kernel_client_stub(node, _tree)
    return _kernel_client_live(_KERNEL_CLIENT, node, _tree)


def _kernel_client_stub(node: FeatureNode, _tree: FeatureTree) -> str:
    """Deterministic hash stub — no real geometry."""
    parent_shape_ids = [(_tree.nodes[parent_id].shape_id or "none") for parent_id in sorted(node.depends_on)]
    payload = {
        "operation": node.operation,
        "parameters": node.parameters,
        "parents": parent_shape_ids,
        "sketch_id": node.sketch_id,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    return f"shape-{node.id}-{digest}"


def _kernel_client_live(client: KernelClient, node: FeatureNode, _tree: FeatureTree) -> str:
    """Execute a feature node through a real kernel client."""
    op_name, params = normalize_feature_operation(node.operation, node.parameters)
    params = resolve_feature_references(params, _tree)

    data = client.call_operation(op_name, params)

    if not data.get("ok", False):
        raise RuntimeError(f"Kernel operation '{op_name}' failed: {data.get('message', 'unknown')}")

    shape_id = data.get("shape_id")
    if not shape_id:
        raise RuntimeError(f"Kernel operation '{op_name}' returned no shape_id.")

    return shape_id


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/trees", response_model=list[str])
def list_trees() -> list[str]:
    return list(_TREES.keys())


@router.post("/trees", response_model=FeatureTree)
def create_tree(tree: FeatureTree) -> FeatureTree:
    FeatureTreeService.ensure_acyclic(tree)
    _TREES[tree.root_id] = tree
    return tree


@router.get("/trees/{tree_id}", response_model=FeatureTree)
def get_tree(tree_id: str) -> FeatureTree:
    return _get_tree_or_404(tree_id)


@router.post("/trees/{tree_id}/nodes", response_model=FeatureTree)
def add_node(tree_id: str, node: FeatureNode) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.add_feature(tree, node)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.post("/trees/{tree_id}/nodes/{node_id}/typed-parameters", response_model=FeatureTree)
def set_typed_parameters(
    tree_id: str,
    node_id: str,
    request: TypedParameterRequest,
) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.set_typed_parameters(
            tree,
            node_id=node_id,
            typed_parameters=request.typed_parameters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.post("/trees/{tree_id}/nodes/{node_id}/suppress", response_model=FeatureTree)
def suppress_node(tree_id: str, node_id: str, request: SuppressFeatureRequest) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.suppress_feature(tree, node_id=node_id, suppressed=request.suppressed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.patch("/trees/{tree_id}/nodes/{node_id}", response_model=FeatureTree)
def edit_node(tree_id: str, node_id: str, request: EditFeatureRequest) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.edit_feature(tree, node_id=node_id, new_params=request.parameters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


def _kernel_segments(sketch: Sketch) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for entity in sketch.entities.values():
        payload = entity.model_dump()
        entity_type = payload["type"]
        if entity_type == "line":
            segments.append({
                "type": "line",
                "start": (payload["x1"], payload["y1"]),
                "end": (payload["x2"], payload["y2"]),
            })
        elif entity_type == "circle":
            segments.append({
                "type": "circle",
                "center": (payload["cx"], payload["cy"]),
                "radius": payload["radius"],
            })
        elif entity_type == "arc":
            start_angle = payload["start_angle"]
            end_angle = payload["end_angle"]
            cx, cy, radius = payload["cx"], payload["cy"], payload["radius"]
            segments.append({
                "type": "arc",
                "center": (cx, cy),
                "radius": radius,
                "start": (cx + radius * math.cos(start_angle), cy + radius * math.sin(start_angle)),
                "end": (cx + radius * math.cos(end_angle), cy + radius * math.sin(end_angle)),
            })
        elif entity_type == "rectangle":
            x, y = payload["x"], payload["y"]
            width, height = payload["width"], payload["height"]
            points = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
            segments.extend(
                {"type": "line", "start": points[index], "end": points[(index + 1) % 4]}
                for index in range(4)
            )
    return segments


@router.put("/trees/{tree_id}/nodes/{node_id}/sketch", response_model=FeatureTree)
def edit_sketch(tree_id: str, node_id: str, sketch: Sketch) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    node = tree.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Feature node '{node_id}' does not exist.")
    if node.operation not in {"add_sketch", "create_sketch"} and node.sketch_id != node.id:
        raise HTTPException(status_code=400, detail=f"Feature node '{node_id}' is not a sketch.")

    segments = _kernel_segments(sketch)
    if not segments:
        raise HTTPException(status_code=400, detail="A rebuildable sketch requires line, circle, arc, or rectangle geometry.")

    existing_order = node.parameters.get("profile_order", [])
    if not isinstance(existing_order, list):
        existing_order = []
    entity_ids = list(sketch.entities)
    profile_order = [entity_id for entity_id in existing_order if entity_id in sketch.entities]
    profile_order.extend(entity_id for entity_id in entity_ids if entity_id not in profile_order)
    parameters = {
        "entities": {key: entity.model_dump() for key, entity in sketch.entities.items()},
        "constraints": [constraint.model_dump(exclude_none=True) for constraint in sketch.constraints],
        "profile_order": profile_order,
        "segments": segments,
    }
    try:
        updated = FeatureTreeService.edit_feature(tree, node_id=node_id, new_params=parameters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.delete("/trees/{tree_id}/nodes/{node_id}", response_model=FeatureTree)
def delete_node(tree_id: str, node_id: str, cascade: bool = Query(default=False)) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.delete_feature(tree, node_id=node_id, cascade=cascade)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.post("/trees/{tree_id}/rebuild", response_model=FeatureTree)
def rebuild_tree(tree_id: str, request: RebuildRequest) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    updated = FeatureTreeService.rebuild(
        tree,
        kernel_client=_kernel_client,
        continue_on_error=request.continue_on_error,
    )
    _TREES[tree_id] = updated
    return updated


@router.post("/trees/{tree_id}/solver/{sketch_id}", response_model=FeatureTree)
def apply_solver_result(tree_id: str, sketch_id: str, request: SolverUpdateRequest) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.apply_solver_result(
            tree,
            sketch_id=sketch_id,
            solved_sketch=request.solved_sketch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.get("/trees/{tree_id}/branches")
def list_branches(tree_id: str) -> dict[str, Any]:
    tree = _get_tree_or_404(tree_id)
    return {
        "active_branch": tree.active_branch,
        "branches": FeatureTreeService.list_branches(tree),
    }


@router.post("/trees/{tree_id}/branches", response_model=FeatureTree)
def create_branch(tree_id: str, request: BranchCreateRequest) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.create_branch(
            tree,
            branch_name=request.branch_name,
            from_branch=request.from_branch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.post("/trees/{tree_id}/branches/{branch_name}/switch", response_model=FeatureTree)
def switch_branch(tree_id: str, branch_name: str) -> FeatureTree:
    tree = _get_tree_or_404(tree_id)
    try:
        updated = FeatureTreeService.switch_branch(tree, branch_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree_id] = updated
    return updated


@router.get("/trees/{tree_id}/serialize")
def serialize_tree(tree_id: str) -> dict[str, str]:
    tree = _get_tree_or_404(tree_id)
    return {"payload": FeatureTreeService.serialize(tree)}


@router.post("/trees/deserialize", response_model=FeatureTree)
def deserialize_tree(request: DeserializeRequest) -> FeatureTree:
    try:
        tree = FeatureTreeService.deserialize(request.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree.root_id] = tree
    return tree


# ── Snapshot / restore ──────────────────────────────────────────────


@router.get("/trees/{tree_id}/snapshot", response_model=TreeSnapshotV1)
def snapshot_tree(tree_id: str) -> TreeSnapshotV1:
    tree = _get_tree_or_404(tree_id)
    return TreeSnapshotV1(tree=tree)


class RestoreSnapshotRequest(BaseModel):
    snapshot: TreeSnapshotV1


@router.post("/trees/restore", response_model=FeatureTree)
def restore_snapshot(request: RestoreSnapshotRequest) -> FeatureTree:
    """Restore a tree from a versioned snapshot."""
    tree = request.snapshot.tree
    try:
        FeatureTreeService.ensure_acyclic(tree)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _TREES[tree.root_id] = tree
    return tree


def create_app() -> FastAPI:
    """Build a standalone feature-tree service app."""
    standalone = create_api_app(title="OpenCAD Feature Tree", version=__version__)
    standalone.include_router(router)
    return standalone


app: FastAPI = create_app()
