# Reconstructing a saved feature tree

A tree JSON file contains modeling instructions, not native B-rep geometry.
`RuntimeContext.load_tree_json()` loads and validates that metadata; call
`rebuild_tree()` to reconstruct the receiving kernel's missing shapes.

```python
from opencad import Part, Sketch
from opencad.kernel.core.occt_backend import OcctBackend
from opencad.runtime import RuntimeContext
from opencad.tree.service import FeatureTreeService

source = RuntimeContext(backend=OcctBackend())
part = Part(context=source).extrude(Sketch(context=source).rect(20, 10), depth=4)
feature_id = part.feature_id
source.save_tree_json("project.json")

restored = RuntimeContext(backend=OcctBackend())
restored.load_tree_json("project.json")
node = restored.rebuild_tree().nodes[feature_id]
if node.status != "built" or node.shape_id is None:
    raise RuntimeError(node.rebuild_error or "Feature is unavailable")
restored.export_step(node.shape_id, "restored.step")

# Continue editing the reconstructed project, using stable feature references.
restored.tree = FeatureTreeService.edit_feature(
    restored.tree, feature_id, {"distance": 6},
)
node = restored.rebuild_tree().nodes[feature_id]
if node.status != "built" or node.shape_id is None:
    raise RuntimeError(node.rebuild_error or "Edited feature is unavailable")
restored.export_step(node.shape_id, "edited.step")
```

The first solid has volume 800; the edited solid has volume 1200. The native
regression tests verify B-rep validity, volume, bounds, and fresh-kernel STEP
import, including a separate Python process that loads, rebuilds, and exports.

## Cold replay versus warm reuse

`FeatureTree.kernel_session_id` is an optional cache-provenance identifier.
Trees from another runtime, including legacy files without this field, do not
retain `built` status. Their executable nodes become stale; the structural
`seed` root remains built without geometry and suppression flags are retained.
Inactive branch snapshots are prepared too, so switching branches cannot
restore phantom built states.

Cold preparation does not execute geometry operations. Each saved result ID
moves to the optional `FeatureNode.replay_shape_id` field and `shape_id` is
cleared until successful reconstruction. The registry's existing checked
`replay_shape_id` mechanism preserves that result identity during execution.
This preserves saved source references and edge/face owner prefixes when the
same feature sequence is replayed. An identity reservation prevents newly
created readable IDs from stealing pending or inactive-branch identities.

The replay field survives save-before-rebuild and failed-operation retries.
On success it is cleared. Shared branch prefixes can reuse results already
replayed by this runtime only when the resolved operation payload matches.
This is not persistent topological naming: changed source geometry, changed
external file contents, or different native-library versions can change the
meaning of positional edge/face indices. Re-select affected subshapes after
source-changing edits; do not assume an old index remains semantically stable.

A foreign tree whose saved result IDs collide with the receiving kernel is
rejected before adoption, rather than overwriting unrelated geometry. Use a
fresh `RuntimeContext` in that case. Raw native input IDs are portable only when
this saved branch contains their producer. Unknown external raw references
fail explicitly; use stable feature references or include an import feature.
Legacy files can be opened in a fresh runtime without migration. A legacy or
foreign file is not treated as a warm cache merely because its ID strings match.

Within the same runtime session, live shapes are retained and unchanged
rebuilds create no additional geometry. Availability checks inspect the owning
backend rather than trusting shape metadata alone. Missing native handles and
unavailable dependencies invalidate the affected nodes. This session marker is
cache metadata, not an authentication mechanism or a geometry-content checksum;
use the feature-edit API to change parameters rather than editing built JSON
records in place.

## Errors, cursors, and external dependencies

`FeatureNode.rebuild_error` contains the operation failure or blocked-dependency
message. Missing STEP/STL inputs include their source path. A failed node is
not built, its dependents are blocked, and it cannot supply a current shape.
Restoring a missing source and rebuilding can retry the saved identity.
`continue_on_error=True` permits independent branches to proceed; it does not
turn failures into successes. Imported files are not embedded or bundled by
saving a tree. Relative paths retain their existing working-directory meaning.
Keep the original input assets and compatible kernel versions for faithful replay.

Feature/sketch counters include inactive branches. Runtime cursors are refreshed
after load and rebuild, and refer to the last available built feature in tree
order (or both are `None`). Existing `Part`/`Sketch` Python objects are not
rebound: use the rebuilt tree's node/shape IDs for subsequent inspection/export.

Runtime replay currently supports the owning **in-process** kernel (native OCCT
or the analytic backend). With an external `KernelClient`, load/rebuild raises
`NotImplementedError` rather than reconstructing into an unrelated local store.
This does not implement remote kernel-session negotiation, bundle import assets,
solve assembly mates, or add general persistent subshape naming.

## Tests

```bash
python scripts/test_occt.py --strict-regressions -k 'cold_reload or saved_tree'
python -m pytest packages/opencad/tests/runtime/test_rehydration.py
python scripts/test_occt.py --strict-regressions
```

The original five audit cases now run as normal regressions, with no retained
expected-failure marker. That does not imply exhaustive CAD operation coverage
or resolution of the separate broader-core-suite failures tracked in #112.
