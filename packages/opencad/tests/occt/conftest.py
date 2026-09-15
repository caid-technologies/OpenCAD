"""Fresh native state per test; only library imports are shared by Python.

Do not session-cache mutable OCCT shapes or a RuntimeContext. Tessellation can
mutate native triangulations, and shared shape stores conceal lifecycle bugs.
"""
from __future__ import annotations

import importlib.util
import math

import pytest


@pytest.fixture(autouse=True)
def require_occt():
    if any(importlib.util.find_spec(name) is None for name in ("cadquery", "OCP")):
        pytest.skip("optional native dependencies absent; use scripts/test_occt.py in CI")


@pytest.fixture()
def backend(require_occt):
    from opencad.kernel.core.occt_backend import OcctBackend

    # UUIDs prevent feature IDs from accidentally matching native shape IDs.
    return OcctBackend(tolerance=1e-6, id_strategy="uuid")


@pytest.fixture()
def registry(backend):
    from opencad.kernel.operations.handlers import OpenCadKernel
    from opencad.kernel.operations.registry import OperationRegistry

    return OperationRegistry(OpenCadKernel(backend=backend))


@pytest.fixture()
def context(backend):
    from opencad.runtime import RuntimeContext

    return RuntimeContext(backend=backend)


@pytest.fixture()
def assert_solid(backend):
    import cadquery as cq
    from OCP.BRepCheck import BRepCheck_Analyzer
    from opencad.kernel.core.models import Success

    def check(result, *, volume=None, solids=1, owner=None):
        source = backend if owner is None else owner
        assert isinstance(result, Success), repr(result)
        assert result.shape is not None and result.shape_id
        native = source.get_native_shape(result.shape_id)
        assert native is not None and not native.IsNull()
        assert BRepCheck_Analyzer(native).IsValid(), "native B-rep is invalid"
        shape = cq.Shape.cast(native)
        assert len(shape.Solids()) == solids, "wrong solid count (a valid shell is not a solid)"
        actual = shape.Volume()
        assert math.isfinite(actual) and actual > 0
        assert result.shape.manifold
        assert result.shape.volume == pytest.approx(actual, rel=1e-9, abs=1e-7)
        if volume is not None:
            assert actual == pytest.approx(volume, rel=1e-7, abs=1e-6)
        assert all(math.isfinite(v) for v in result.shape.bbox.model_dump().values())
        assert len(set(result.shape.edge_ids)) == len(result.shape.edge_ids)
        assert len(set(result.shape.face_ids)) == len(result.shape.face_ids)
        return shape

    return check


@pytest.fixture()
def rectangle():
    def segments(width, height, *, x=0.0, y=0.0):
        points = [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
        return [
            {"type": "line", "start": start, "end": end}
            for start, end in zip(points, points[1:] + points[:1])
        ]
    return segments
