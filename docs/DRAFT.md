# Draft / taper

`draft` uses OCCT's `BRepOffsetAPI_DraftAngle` on selected planar, cylindrical,
or conical faces of a valid solid. The operation returns new geometry and
leaves its input shape available. The analytic backend is a lightweight
approximation; use the OCCT backend to verify a real taper.

## API and coordinate conventions

```python
part.draft(
    face_ids=[side_face_id],
    angle=5.0,
    pull_direction=(0.0, 0.0, 1.0),
    neutral_plane_origin=(0.0, 0.0, 0.0),
    neutral_plane_normal=None,
)
```

The registry operation `draft` accepts the same geometric fields plus
`shape_id`. `face_ids`, `shape_id`, and `angle` remain the only required
schema fields. Existing calls without neutral-plane parameters still work.

`angle` is in **signed degrees**, with magnitude greater than the kernel's
angular check tolerance and less than 90 degrees. `pull_direction` is a
non-zero world-space vector; it need not have unit length. Coordinates are
in the model's length units. Angles and vector components must be finite.

`neutral_plane_origin` is a point on the plane in **world coordinates**,
not an offset relative to the part. Its default is the world origin.
`neutral_plane_normal` is a non-zero world-space vector. When omitted or
`None`, it follows `pull_direction`, so the default plane is perpendicular
to the pull direction even when pulling along X or Y instead of Z.
An explicitly supplied normal can define an oblique neutral plane.

The intersection of the original face and neutral plane remains fixed.
For sides initially parallel to the pull axis, positive angles taper inward
on the pull side of the plane; negative angles taper outward. If the plane intersects the part's interior, material can be
added on one side and removed on the other, so volume alone does not prove
that a taper occurred. OCCT measures curved-face draft relative to the pull
axis: it is not an incremental addition to an existing cone's half angle.
For an already steeply tapered cone, a smaller positive draft angle can
therefore increase rather than reduce its volume.

## Translated part example

```python
from opencad import Part
from opencad.kernel.core.occt_backend import OcctBackend
from opencad.runtime import RuntimeContext

context = RuntimeContext(backend=OcctBackend())
part = Part(context=context).box(10, 10, 10).translate((12, -7, 20))
side = max(context.get_topology(part.shape_id).faces,
           key=lambda face: face.centroid[0])
part.draft(
    face_ids=[side.id],
    angle=5,
    neutral_plane_origin=(12, -7, 15),  # bottom plane of this translated box
)
part.export_step("drafted.step")
```

The +X face stays fixed at Z=15 and moves inward by `10 * tan(5 degrees)`
at Z=25. To anchor a translated part, translate the neutral-plane point
explicitly; the default is intentionally not silently moved with the part.

## Validation and rebuild scope

Draft rejects foreign, stale, out-of-range, duplicate, and edge references
used as face IDs. Spherical and toroidal faces are unsupported. OCCT may
also reject a supported face whose pull/neutral-plane setup is incompatible,
or a taper that collapses geometry. Tangential propagation follows OCCT's
rules; this operation does not promise topology-changing draft repair.

Each face addition is checked with `AddDone()`. A failed addition or build,
a null/invalid result, or a result with missing/zero-volume solids returns a
structured failure rather than registering a partial or false-success shape.

The fluent API stores the angle, pull direction, and both neutral-plane
parameters in the feature tree. Editing those parameters and rebuilding
against the same owning kernel is covered, including serialization followed
by repeated edits and STEP round-trip verification. Explicit face references
remain scoped to the source shape: after replacing upstream geometry, reselect
faces from that new shape. General persistent topological naming and cold
rehydration of serialized projects (#110) are outside this fix.

## Tests

From the repository root, using the native environment described in
[OCCT_TESTING.md](OCCT_TESTING.md):

```bash
python scripts/test_occt.py --strict-regressions -k draft
python scripts/test_occt.py --junitxml=test-results/occt.xml
```

Draft's OCCT-001 regression is no longer an expected failure. The other four
audited failures (#107–#110) remain independently tracked. Tests compare
analytic side-plane equations, rim positions, signed volume changes,
translated/oblique planes, non-Z pulls, curved faces, and state preservation.

Native API reference:
[OCCT BRepOffsetAPI_DraftAngle](https://dev.opencascade.org/doc/occt-7.8.0/refman/html/classBRepOffsetAPI__DraftAngle.html).
