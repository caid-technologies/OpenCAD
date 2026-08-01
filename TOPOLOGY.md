# Topology Reference Stability

> **Status:** Open research question
> **Blocks:** Phase 2 part-level 3-D constraints
> **Context:** Phase 1 (assembly mates between shapes) ships without stable topology
> references because mates address whole-shape faces via synthetic IDs generated at
> creation time.  Part-level constraints (constraining *specific* faces/edges that
> survive parametric rebuilds) require a fundamentally different identity contract

---

## The Problem

When a user constrains *Face A* of a box, then edits a feature upstream (adds a
fillet, changes a boolean), the kernel rebuilds the shape.  After rebuild, the face
that was previously *Face A* may:

- still exist but have a different index,
- be split into multiple faces,
- be merged with an adjacent face, or
- no longer exist at all.

If the constraint still points to `box-0001:face:0`, it silently refers to the
**wrong geometry** — or worse, to nothing.  The constraint system reports a
confusing error, the user loses trust, and the AI agent cannot reason about valid
references.

### Failure Walkthrough

```text
Step 1:  Create box   → box-0001 with 6 faces (face:0 = top, face:1 = bottom, …)
Step 2:  Add mate     → coincident(box-0001:face:0, cyl-0001:face:0)   ✓ works
Step 3:  Fillet edge  → box-0001 rebuilt as fillet-0001 with 7+ faces
Step 4:  Mate breaks  → fillet-0001:face:0 is now a fillet blend surface
                         The original "top" face is now face:3 (or split into two)
                         Constraint silently targets wrong geometry  ✗
```

This is the **topological naming problem** — the single hardest unsolved UX issue
in parametric CAD.  Every major system has attempted a solution; none are fully
satisfactory.

---

## Known Approaches

### 1. Persistent IDs via Operation History (OpenCascade TNaming)

**How it works:**  Each modeling operation records which input faces it consumed
and which output faces it produced in a *naming log*.  Face identity is derived
from the chain of operations that created it, not from its geometric index.
OpenCascade's `TNaming` package implements this as a label tree where each node
carries a `NamedShape` with `Evolution` tags (GENERATED, MODIFIED, DELETE, etc.).

**Tradeoffs:**

| Pro | Con |
|-----|-----|
| Proven in production (SALOME, FreeCAD via OCC) | Complex implementation (~15k LOC in OCC) |
| Survives most parametric edits | Fragile across boolean topology changes |
| Well-documented algorithm family | Tight coupling to the B-Rep kernel's internal face splitting |

**Prior art — FreeCAD's TNaming saga:**

FreeCAD adopted OpenCascade's TNaming as its topology stabilisation strategy.
The result has been a years-long, partially successful effort:

- Face references break after certain boolean operations and fillets.
- The `topological naming` branch (Realthunder's fork) added a parallel
  naming system that improved stability but introduced maintenance burden
  and merge conflicts with upstream.
- As of 2025, FreeCAD 1.0 ships with partial TNaming support.  Users still
  encounter broken references in complex models with stacked booleans.
- **Lesson:** TNaming works for simple linear histories but degrades in
  branching / boolean-heavy workflows that are common in real parts.

**Key failure modes to avoid:**

- Boolean cuts that split a tracked face into N fragments — the naming log
  must handle fan-out, and consumers must choose *which* fragment to follow.
- Feature reorder — swapping two operations invalidates the naming chain if
  it depends on insertion order rather than geometric semantics.

### 2. Hash-Based Face Tracking

**How it works:**  Each face is fingerprinted by a hash of its geometric
properties (surface type, normal, centroid, area, bounding UV domain).  After
rebuild, faces are matched by closest hash similarity.

**Tradeoffs:**

| Pro | Con |
|-----|-----|
| Simple to implement (~200 LOC) | Ambiguous when faces have identical geometry (symmetry) |
| Kernel-agnostic (works across OCC, Manifold, etc.) | Fails on near-degenerate geometry (tiny fillets, tangent surfaces) |
| No operation-history dependency | Cannot distinguish split/merged faces |

**Prior art — Build123d:**

Build123d uses geometric hashing internally to support its selector system.
The current implementation:

- Works well for prismatic parts with clearly distinct faces.
- Breaks on symmetric bodies (e.g., a cube where all 6 faces have equal area)
  — the hash cannot distinguish them without positional context.
- Does not track face splits: if a fillet splits a planar face into a
  planar remainder and a blend surface, the hash matcher may pick the
  wrong one.
- **Lesson:** Hashing is a good *fallback* or *secondary signal*, but
  cannot serve as the sole identity mechanism for production parametric
  constraints.

**Key failure modes to avoid:**

- Symmetric models where multiple faces share identical hash fingerprints.
- Incremental edits that change centroid/area by small amounts, causing
  the closest-hash match to jump between candidates.

### 3. Parametric Graph Position Tracking (Fusion 360 Internal Approach)

**How it works:**  Each face is identified by its position in the parametric
feature graph — which operation created it, which input face it derived from,
and a local index within that operation's output.  This is conceptually similar
to TNaming but implemented as graph-node metadata rather than a separate label
tree.

**Tradeoffs:**

| Pro | Con |
|-----|-----|
| Natural fit for feature-tree architectures | Requires tight integration with every operation handler |
| Handles feature reorder better than pure TNaming | Proprietary — limited public documentation |
| Graph-native introspection (which op affects which face) | Scales poorly for imported geometry (no feature graph) |

**Observations:**

- Fusion 360's approach is documented only through reverse-engineering and
  informal Autodesk blog posts.  The exact algorithm is proprietary.
- It handles feature reorder and suppression gracefully because identity is
  *graph-relative* (parent op + local index), not *history-absolute*.
- For imported STEP files with no parametric history, Fusion falls back to
  heuristic matching.
- **Lesson:** Graph-relative identity is the most robust known approach for
  parametric-native models, but requires every operation to participate in
  the identity protocol.

### 4. Occurrence Path References (STEP Assembly / IGES Approach)

**How it works:**  In STEP AP214/AP242 assemblies, a face is addressed by
its *occurrence path*: a chain of component instance references leading
down to the specific B-Rep face.  Identity is structural (path in the
assembly tree) rather than geometric or historical.

**Tradeoffs:**

| Pro | Con |
|-----|-----|
| Unambiguous within a single assembly state | Does not survive parametric rebuild — it's a snapshot |
| ISO standard — interoperable across systems | Requires full assembly-tree structure |
| Good for inter-system exchange | No concept of "same face after edit" |

**Observations:**

- Occurrence paths work for static assembly references (e.g., bolted joint
  between Comp A face 3 and Comp B face 7).
- They **do not** solve the parametric naming problem because the path is
  invalidated whenever the assembly structure changes.
- Useful as a *wire format* for exchanging constraint references, but not
  as an identity database.
- **Lesson:** Good complement to a parametric identity system, not a
  replacement.

---

## How This Fits OpenCAD's Architecture

OpenCAD's current topology system (`opencad/kernel/core/topology.py`) uses
**synthetic face generation** based on shape kind and bounding box.  This is
sufficient for Phase 1 assembly mates (which target entire shape faces by
index) but will not survive:

- Boolean edits that change face count
- Fillets/chamfers that split faces
- Feature reorder in the parametric tree

Any Phase 2 proposal must integrate with:

- **Kernel backend protocol** (`packages/opencad/src/opencad/kernel/core/backend.py`) — topology
  identity must work across analytic and OCCT backends.
- **Operation registry** (`opencad/kernel/operations/registry.py`) — every
  registered operation must participate in the identity protocol.
- **Feature tree** (`opencad/tree/`) — face identity must compose with the
  existing DAG rebuild and stale-propagation semantics.
- **Solver diagnostics** (`opencad/solver/`) — the constraint introspection
  API should be able to report *which face references are stale*.

---

## Do Not Repeat Known Failures — Proposal Checklist

Before submitting a topology reference proposal, ensure your design addresses
these failure modes observed in FreeCAD TNaming and Build123d hash tracking:

- [ ] **Boolean fan-out:** A face split by a boolean cut into N fragments.
      Which fragment does the constraint follow?  What if the user wanted the
      *other* fragment?
- [ ] **Fillet/chamfer face splitting:** A planar face adjacent to a filleted
      edge gets split into planar + blend.  How is the old reference
      disambiguated?
- [ ] **Feature reorder:** Swapping two operations in the tree.  Does the
      face identity survive, or is it path-dependent?
- [ ] **Symmetric geometry:** A cube with 6 identical-area faces.  Can the
      system distinguish "top" from "bottom" after a 90° rotation feature?
- [ ] **Imported geometry:** A STEP file with no parametric history.  How
      are faces identified and tracked across subsequent edits?
- [ ] **Backend portability:** Does the approach work equally well with
      the analytic backend AND the OCCT backend?
- [ ] **Agent reasoning:** Can an AI agent query the identity system to
      determine "is this the same face I constrained earlier?"

---

## Call for Proposals

We are evaluating:

1. **Persistent face IDs** (TNaming-style)
2. **Hash-based face tracking** (geometric fingerprinting)
3. **Parametric graph position tracking** (Fusion-style graph-relative identity)
4. **Occurrence path references** (STEP-style structural paths)
5. **Hybrid approaches** combining two or more of the above

### What a proposal should include

1. **Design rationale** — why this approach fits OpenCAD's modular,
   multi-backend architecture better than the alternatives.
2. **Data model sketch** — what gets stored per face, per operation, and per
   rebuild cycle.
3. **API shape** — how downstream consumers (solver, tree, agent) query and
   validate face identity.
4. **Migration path** — how the current synthetic topology system evolves
   into the proposed identity system without breaking Phase 1 assembly mates.
5. **Prior-art comparison** — explicit comparison with FreeCAD TNaming and
   Build123d hash tracking, explaining how your design avoids their known
   failure modes.
6. **Validation matrix** — test scenarios covering the checklist above, with
   expected behavior for each.

### Acceptance criteria

- Covers all items in the "Do Not Repeat Known Failures" checklist.
- Demonstrates a working prototype against at least 3 test scenarios
  (boolean, fillet, feature reorder).
- Compares explicitly against FreeCAD TNaming and Build123d results for the
  same scenarios.
- Does not require changes to the solver or tree service APIs beyond additive
  fields.

A working proposal with implementation sketch will unblock Phase 2.

---

## Discussion

Open an issue or PR tagged `topology-stability` to propose or discuss approaches.
This is an open contribution opportunity — people who've thought deeply about
parametric stability are exactly who we want working on this.
