# Geometric top-edge selection

`Part.fillet(edges="top", ...)` and `Part.chamfer(edges="top", ...)` select
**all non-degenerate edges lying wholly in the shape's highest world-Z plane**.
They do not select the first four edges, the edges with the highest midpoint,
all upward-facing boundaries, or a camera/workplane-relative direction.

```python
from opencad import Part
from opencad.kernel.core.backend_factory import create_backend
from opencad.runtime import RuntimeContext

context = RuntimeContext(backend=create_backend("occt", require_native=True))
part = Part(context=context).box(20, 12, 6).translate((10, -5, 30))
part.fillet(edges="top", radius=0.5)  # upper rim at world Z = 33
```

Use `chamfer(edges="top", distance=0.5)` in place of `fillet` for a bevel.
A geometrically correct selection does not guarantee that every requested
radius/distance is buildable; native feature construction may still reject it.

## Definition and supported geometry

The OCCT backend calculates a geometric bounding box for the entire shape.
It tags an edge `top` only when both that edge's minimum and maximum Z are
within the comparison tolerance of the shape's maximum Z. A centroid test is
only a prefilter: complete curve bounds must also pass. Degenerate pole edges
and edges no longer than the comparison tolerance are excluded.

The comparison tolerance is `max(backend.tolerance, 1e-7)` in model units
(the normal backend default is `1e-6`). The floor matches OCCT's geometric
confusion tolerance. Comparisons are absolute, not relative to the distance
from the origin, so translating a small part far from the origin does not
turn its vertical or lower edges into top edges.

Supported examples include the upper rectangular rims of centered/translated
boxes and principal-plane extrusions, circular rims of vertical cylinders and
truncated cones, and **both outer and inner/hole rims** of a flat-topped plate.
There is no hard-coded edge count. Equal-height patterned bodies contribute
all qualifying edges; on a stepped part, only the globally highest edges
qualify. On sloped geometry a horizontal ridge at maximum Z can qualify even
though it is not a closed rim. This selector does not mean "per-body top" or
"edges of the topmost face".

Spheres, pointed cones, tori, and tilted cylinders without any complete edge
in the highest horizontal plane have no matching rim. `top` raises
`ValueError` before running the fillet/chamfer or appending a feature. It never
falls back to arbitrary edges or treats a degenerate apex as a usable rim.

## Local and service-backed runtimes

The owning native kernel supplies the geometric `top` tag through the existing
`SubshapeRef.tags` field in its topology response. `Part` consumes those tags
through `RuntimeContext.get_topology`, so it does not need local access to a
remote kernel's OCCT objects. No transport/schema change is required. Existing
face tags describe normals; the **edge** `top` tag instead describes position
of the entire edge in the maximum-Z support plane.

The analytic backend has synthetic edge centroids and cannot certify this
geometry. It therefore rejects `top` rather than retaining the old arbitrary
four-edge fallback. Use an OCCT-backed context for geometric selection. A
remote backend that does not report the new tags also fails explicitly; update
the server or supply explicit edge IDs instead.

`edges=None`, `edges="all"`, and explicit ID lists retain their prior behavior,
including explicit-list order and the kernel's existing validation.

## Scope and verification

This fixes #107 (OCCT-002). The original native regression is now an ordinary
passing test. `tests/occt/test_top_edges.py` checks translations and scales,
reordered metadata, actual upper-only material removal, circular and hole rims,
steps/patterns, non-XY sketches, coarse tessellation, STEP round trips, and
serialized remote topology. Analytic refusal and unchanged selector options
are also tested without requiring native dependencies.

Bounds are obtained using `BRepBndLib.AddOptimal` with triangulation and
shape-tolerance inflation disabled, so display-mesh resolution is not the
source of truth for selection. Reference: [OCCT BRepBndLib](https://dev.opencascade.org/doc/occt-7.8.0/refman/html/classBRepBndLib.html).

Selections are resolved for the **current source shape**; the feature tree
still stores concrete edge IDs. This fix does not add persistent topological
naming, automatic selection re-resolution after replacing upstream geometry,
or cold project rehydration. Those capabilities must not be inferred from a
passing top-selector test.

After installing the environment in [OCCT_TESTING.md](OCCT_TESTING.md), run
these focused checks from the repository root:

```bash
python scripts/test_occt.py --strict-regressions -k test_top_
python -m pytest packages/opencad/tests/runtime/test_edge_selection.py
```
