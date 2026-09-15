"""No native dependencies are needed to check unavailable-selector behavior."""
import pytest

from opencad import Part
from opencad.kernel.core.analytic_backend import AnalyticBackend
from opencad.runtime import RuntimeContext


@pytest.mark.parametrize("operation", ["fillet", "chamfer"])
def test_analytic_top_selection_requires_certified_geometry(operation):
    context = RuntimeContext(backend=AnalyticBackend())
    part = Part(context=context).box(10, 10, 10)
    before_tree = context.serialize_tree()
    before_ids = context.kernel.store.all_ids()
    with pytest.raises(ValueError, match="OCCT-backed context"):
        getattr(part, operation)(edges="top", **({"radius": 1} if operation == "fillet" else {"distance": 1}))
    assert context.serialize_tree() == before_tree
    assert context.kernel.store.all_ids() == before_ids
    assert len(part._resolve_edge_ids("all")) == 12


def test_unsupported_edge_selector_still_rejected():
    part = Part(context=RuntimeContext(backend=AnalyticBackend())).box(10, 10, 10)
    with pytest.raises(ValueError, match="Unsupported edge selector"):
        part._resolve_edge_ids("topp")
