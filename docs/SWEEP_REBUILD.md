# Rebuilding a sweep after sketch edits

A fluent `Part.sweep(profile, path)` stores **feature-node references** in
`profile_id` and `path_id`. Both sketches are dependency-graph inputs. Editing
either sketch invalidates the sweep and its downstream features; rebuilding
must use each input's current kernel shape, not the shape created initially.

The shared scalar-reference resolver translates both fields into current shape
IDs only in the operation payload. It does not overwrite the saved references,
so subsequent edits and same-kernel JSON round trips continue to work. This
resolver is used by both the in-process feature executor and the backend's live
kernel-client executor. The native tests here exercise the in-process path;
they do not certify live HTTP transport or external-runtime ownership.

## Example: change the section radius

```python
from copy import deepcopy
from opencad import Part, Sketch
from opencad.kernel.core.occt_backend import OcctBackend
from opencad.runtime import RuntimeContext
from opencad.tree.service import FeatureTreeService

ctx = RuntimeContext(backend=OcctBackend(id_strategy="uuid"))
profile = Sketch(context=ctx).circle(2)
path = Sketch(context=ctx, plane="XZ").line((0, 0), (0, 10))
part = Part(context=ctx).sweep(profile, path)
sweep_id = part.feature_id

segments = deepcopy(ctx.tree.nodes[profile.feature_id].parameters["segments"])
segments[0]["radius"] = 3
ctx.tree = FeatureTreeService.edit_feature(
    ctx.tree, profile.feature_id, {"segments": segments},
)
rebuilt = ctx.rebuild_tree().nodes[sweep_id]
if rebuilt.status != "built" or rebuilt.shape_id is None:
    raise RuntimeError("Sweep did not rebuild")
ctx.export_step(rebuilt.shape_id, "rebuilt-sweep.step")
```

For this circular section and straight path, the rebuilt volume is `90 * pi`.
To edit the path length, similarly update the stored line segment's `end`, then
rebuild. Read the current shape ID from the returned tree: pre-existing `Part`
or `Sketch` Python objects and runtime cursors are not automatically rebound by
this fix. Old native shapes may remain in the kernel as immutable prior results.

## Reference validation and compatibility

- A reference matching a tree node resolves only when that node is built,
  unsuppressed, and has a non-empty shape ID. A stale/failed/pending/suppressed
  node must never contribute cached geometry just because its old ID survives.
- A known but unavailable node causes the resolver to raise `ValueError`, naming
  the field and source node. The tree rebuild service retains its existing
  failed/blocked status behavior; it does not return that exception as new
  structured error metadata. A missing declared graph dependency raises
  `MissingDependencyError` before execution.
- Literal native IDs not matching tree nodes remain supported. The owning kernel
  validates their availability. They refer to specific immutable geometry, not
  editable feature dependencies, and are not automatically redirected on edits.
- Unrelated strings, nested settings, and lists are not rewritten. The declared
  loft `profile_ids` list is resolved separately; see [LOFT_REBUILD.md](LOFT_REBUILD.md).
  Existing scalar reference fields share the readiness check. Valid built-node
  references remain compatible.

## Tests and scope

```bash
python scripts/test_occt.py --strict-regressions -k 'sweep_rebuild or (profile_references_survive_rebuild and sweep)'
python -m pytest packages/opencad/tests/runtime/test_sweep_references.py
```

Native coverage includes separate profile/path edits, repeated edits, dependent
translation, unchanged rebuilds, non-Z paths and translated geometry, suppression
and recovery, failed input builds, missing references/geometry, JSON round trips
in the owning kernel, and exporting/reimporting a rebuilt sweep via STEP. Tests
use UUID native IDs to prevent accidental equality with feature IDs.

This repairs **#108**. Ordered loft references are also repaired in **#109**; cold
project reconstruction into a new kernel remains **#110**. This does not change
sweep geometry algorithms, infer graph dependencies when manually replacing
reference fields, or implement persistent topological naming.
