# Rebuilding a loft after section edits

`Part.loft(sketches, solid=True, ruled=False)` stores the sketches' **feature
IDs in their supplied order** in `profile_ids`. Editing an input sketch
invalidates the loft and its downstream features. On rebuild, the shared
reference resolver produces an ordered list of the inputs' current native
shape IDs for the kernel call, without modifying the saved feature references.

It neither sorts sections by feature ID, graph order, or position nor removes
duplicates. Sketch creation order does not define loft order. Repeated references
are preserved in the payload, but that is not a promise that repeated/coincident
sections form valid geometry: the native loft algorithm still decides that.
`solid` and `ruled` retain their existing meaning and are passed through unchanged.

## Example: edit the first section and export the rebuilt loft

```python
from copy import deepcopy

from opencad import Part, Sketch
from opencad.kernel.core.occt_backend import OcctBackend
from opencad.runtime import RuntimeContext
from opencad.tree.service import FeatureTreeService

ctx = RuntimeContext(backend=OcctBackend(id_strategy="uuid"))
first = Sketch(context=ctx).circle(2)
last = Sketch(context=ctx, origin=(0, 0, 10)).circle(1)
part = Part(context=ctx).loft([first, last], ruled=True)
loft_id = part.feature_id

segments = deepcopy(ctx.tree.nodes[first.feature_id].parameters["segments"])
segments[0]["radius"] = 3
ctx.tree = FeatureTreeService.edit_feature(
    ctx.tree, first.feature_id, {"segments": segments},
)
rebuilt = ctx.rebuild_tree().nodes[loft_id]
if rebuilt.status != "built" or rebuilt.shape_id is None:
    raise RuntimeError("Loft did not rebuild")
ctx.export_step(rebuilt.shape_id, "rebuilt-loft.step")
```

The resulting coaxial conical frustum has volume `130 * pi / 3`. To edit a
middle or final section, edit that sketch's stored parameters in the same way.
Use the rebuilt tree's shape ID for inspection/export; existing `Part`/`Sketch`
objects and runtime cursors are not automatically rebound by this repair.

## Validation and compatibility

Only declared reference fields are resolved. `profile_ids` is the ordered
list-valued field; existing scalar fields, including sweep's `profile_id` and
`path_id`, share the same source-readiness check. A list is copied; an ordered
Python tuple is normalized to a list in the execution payload. Unrelated lists,
nested settings, names, and edge/face IDs are not recursively rewritten.

A reference matching a tree node must point to a built, unsuppressed node with
a non-empty shape ID. Otherwise the resolver raises `ValueError` with the
field, zero-based list index, and feature ID (for example, `profile_ids[1]`).
An old cached shape does not make a stale/failed/pending/suppressed feature usable.
The input parameters and tree are unchanged even if resolution fails partway
through a list. Invalid element types and malformed payloads still fail schema
validation at the registry rather than being dropped or coerced by the resolver.

Literal native IDs not matching a tree node remain supported, including alongside
feature references. The owning kernel validates their presence. They refer to
specific immutable geometry, not editable graph dependencies. A missing declared
graph input raises `MissingDependencyError`; other execution failures retain
the existing tree service's failed/blocked status behavior. This repair does not
introduce structured rebuild-error metadata.

## Tests and scope

```bash
python scripts/test_occt.py --strict-regressions -k 'loft_rebuild or (profile_references_survive_rebuild and loft)'
python -m pytest packages/opencad/tests/runtime/test_loft_references.py packages/opencad/tests/runtime/test_sweep_references.py
```

Native coverage checks edits to either end and every position in a three-section
loft, both forward/reverse declared orders, out-of-order sketch creation,
repeated edits and dependent translation, unchanged rebuilds, translated/non-Z
sections, open shells, missing inputs, stale cached shapes, suppression and
failure recovery, same-owning-kernel JSON round trips, and fresh-kernel STEP
import of the rebuilt result. UUID native IDs prevent accidental equality with
feature IDs from hiding the defect. Lightweight tests additionally verify
payload order, duplicate preservation, tuple inputs, and error indices.

This repairs **#109** on top of the scalar resolver from **#108**. Cold project
rehydration into an empty kernel remains **#110**; the JSON tests here deliberately
reuse the owning kernel. The native tests exercise in-process execution, not
live HTTP or external-runtime kernel ownership. Loft geometry algorithms, automatic
graph rewiring when replacing references by hand, and persistent subshape naming
are unchanged.
