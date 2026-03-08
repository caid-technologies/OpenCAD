"""
Example 01 — Hello Part
=======================
A "hello world" for the OpenCAD headless fluent API.

Demonstrates:
  - Creating primitive shapes (box, cylinder)
  - Boolean cut (subtract one shape from another)
  - Edge fillet
  - Feature-tree inspection
  - STEP export

No HTTP services are required; everything runs in a single Python process.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from opencad import Part, Sketch, get_default_context, reset_default_context


def main() -> None:
    # Always reset the default context so each run starts from a clean state.
    reset_default_context()

    # ── 1. Create a rectangular base block ──────────────────────────────
    base = Part(name="Base")
    base.box(length=80, width=60, height=20)
    print(f"✅ Created box:       {base.feature_id}  shape_id={base.shape_id}")

    # ── 2. Create a cylinder to use as a hole ───────────────────────────
    hole = Part(name="Hole")
    hole.cylinder(radius=10, height=25)
    print(f"✅ Created cylinder:  {hole.feature_id}  shape_id={hole.shape_id}")

    # ── 3. Subtract the cylinder from the base block ────────────────────
    base.cut(hole, name="CutHole")
    print(f"✅ Boolean cut:       {base.feature_id}")

    # ── 4. Round off some edges ──────────────────────────────────────────
    base.fillet(edges="top", radius=3, name="TopFillet")
    print(f"✅ Fillet:            {base.feature_id}")

    # ── 5. Inspect the feature tree ─────────────────────────────────────
    ctx = get_default_context()
    node_count = len(ctx.tree.nodes)
    print(f"Feature tree has {node_count} nodes (including root)")

    # Pretty-print the feature node names and operations for clarity.
    for node_id, node in ctx.tree.nodes.items():
        print(f"  [{node.status:>10}]  {node_id:12}  op={node.operation}  name={node.name!r}")

    # ── 6. Export to STEP ────────────────────────────────────────────────
    output_path = Path(tempfile.gettempdir()) / "hello_part.step"
    base.export(str(output_path))
    print(f"✅ Exported to {output_path}")

    # ── 7. (Optional) Dump the tree as JSON for inspection ──────────────
    tree_json = ctx.tree.model_dump()
    json_path = Path(tempfile.gettempdir()) / "hello_part_tree.json"
    json_path.write_text(json.dumps(tree_json, indent=2))
    print(f"✅ Tree JSON written to {json_path}")


if __name__ == "__main__":
    main()
