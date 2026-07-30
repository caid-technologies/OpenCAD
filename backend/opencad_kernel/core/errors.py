from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    SHAPE_NOT_FOUND = "SHAPE_NOT_FOUND"
    ZERO_VOLUME = "ZERO_VOLUME"
    BBOX_NO_OVERLAP = "BBOX_NO_OVERLAP"
    BBOX_NEAR_TANGENT = "BBOX_NEAR_TANGENT"
    NON_MANIFOLD = "NON_MANIFOLD"
    BOOLEAN_KERNEL_ERROR = "BOOLEAN_KERNEL_ERROR"
    FILLET_RADIUS_TOO_LARGE = "FILLET_RADIUS_TOO_LARGE"
    CHAMFER_FAILURE = "CHAMFER_FAILURE"
    SHELL_FAILURE = "SHELL_FAILURE"
    DRAFT_FAILURE = "DRAFT_FAILURE"
    OFFSET_COLLAPSE = "OFFSET_COLLAPSE"
    SWEEP_FAILURE = "SWEEP_FAILURE"
    LOFT_FAILURE = "LOFT_FAILURE"
    REVOLVE_FAILURE = "REVOLVE_FAILURE"
    SKETCH_ERROR = "SKETCH_ERROR"
    EXTRUDE_FAILURE = "EXTRUDE_FAILURE"
    PATTERN_ERROR = "PATTERN_ERROR"
    MIRROR_FAILURE = "MIRROR_FAILURE"
    TOPOLOGY_ERROR = "TOPOLOGY_ERROR"
    IO_ERROR = "IO_ERROR"
    UNSUPPORTED_STEP = "UNSUPPORTED_STEP"
    UNSUPPORTED_FILE_FORMAT = "UNSUPPORTED_FILE_FORMAT"
    # Assembly constraint errors
    MATE_INVALID_REFERENCE = "MATE_INVALID_REFERENCE"
    MATE_UNSATISFIED = "MATE_UNSATISFIED"
    MATE_SINGULAR_SYSTEM = "MATE_SINGULAR_SYSTEM"
    MATE_DUPLICATE = "MATE_DUPLICATE"
    MATE_NOT_FOUND = "MATE_NOT_FOUND"
    SOLVER_BACKEND_UNAVAILABLE = "SOLVER_BACKEND_UNAVAILABLE"


class Failure(BaseModel):
    ok: bool = Field(default=False)
    code: ErrorCode
    message: str
    suggestion: str
    failed_check: Optional[str] = None


def make_failure(
    code: ErrorCode,
    message: str,
    suggestion: str,
    failed_check: Optional[str] = None,
) -> Failure:
    return Failure(
        code=code,
        message=message,
        suggestion=suggestion,
        failed_check=failed_check,
    )
