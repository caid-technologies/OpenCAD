from __future__ import annotations

from .errors import ErrorCode, Failure, make_failure
from .geometry import overlap_volume
from .models import ShapeData


def check_nonzero_volume(shape: ShapeData, tolerance: float) -> Failure | None:
    if shape.volume <= tolerance:
        return make_failure(
            code=ErrorCode.ZERO_VOLUME,
            message=f"Shape '{shape.id}' has zero or near-zero volume.",
            suggestion="Regenerate the shape with larger dimensions.",
            failed_check="nonzero_volume",
        )
    return None


def check_manifold(shape: ShapeData) -> Failure | None:
    if not shape.manifold:
        return make_failure(
            code=ErrorCode.NON_MANIFOLD,
            message=f"Shape '{shape.id}' is not manifold.",
            suggestion="Heal or recreate the input shape before Boolean operations.",
            failed_check="manifold",
        )
    return None


def check_bbox_overlap(a: ShapeData, b: ShapeData, tolerance: float) -> Failure | None:
    ov = overlap_volume(a.bbox, b.bbox)
    if ov <= 0.0:
        return make_failure(
            code=ErrorCode.BBOX_NO_OVERLAP,
            message=f"Bounding boxes for '{a.id}' and '{b.id}' do not overlap.",
            suggestion="Move shapes closer together before union/intersection.",
            failed_check="bbox_overlap",
        )
    if ov <= tolerance:
        return make_failure(
            code=ErrorCode.BBOX_NEAR_TANGENT,
            message=(
                f"Bounding boxes for '{a.id}' and '{b.id}' are near-tangent (overlap {ov:.3e})."
            ),
            suggestion="Increase overlap or relax tolerance for near-tangent geometry.",
            failed_check="bbox_overlap",
        )
    return None
