"""
Example 02 — Parametric Bracket
================================
Builds a flat mounting bracket with evenly spaced bolt holes using the
OpenCAD headless fluent API.

Design parameters (edit freely):
  PLATE_LENGTH  — overall length of the bracket in mm
  PLATE_WIDTH   — overall width of the bracket in mm
  PLATE_THICK   — thickness of the bracket in mm
  HOLE_RADIUS   — radius of each bolt hole in mm
  HOLE_COUNT    — number of bolt holes along the length
  FILLET_R      — edge fillet radius in mm

No HTTP services are required.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from opencad import Part, Sketch, get_default_context, reset_default_context

# ── Design parameters ────────────────────────────────────────────────────────
PLATE_LENGTH: float = 120.0  # mm
PLATE_WIDTH: float = 40.0   # mm
PLATE_THICK: float = 8.0    # mm
HOLE_RADIUS: float = 4.0    # mm
HOLE_COUNT: int = 8          # number of bolt holes
FILLET_R: float = 2.0       # edge fillet radius


def main() -> None:
    reset_default_context()

    # ── 1. Draw the base-plate profile and extrude ───────────────────────
    # A simple rectangle profile — no cut-out in the sketch because we
    # subtract the bolt holes as separate boolean operations later.
    plate_sketch = Sketch(name="PlateProfile", plane="XY")
    plate_sketch.rect(PLATE_LENGTH, PLATE_WIDTH)

    plate = Part(name="BracketBase")
    plate.extrude(plate_sketch, depth=PLATE_THICK, name="BasePlate")
    print(f"✅ Base plate extruded  {plate.feature_id}")

    # ── 2. Create a single bolt-hole cylinder ────────────────────────────
    # The hole is taller than the plate so the boolean cut goes all the way
    # through regardless of floating-point edge cases.
    bolt_hole = Part(name="BoltHole")
    bolt_hole.cylinder(radius=HOLE_RADIUS, height=PLATE_THICK + 2)
    print(f"✅ Bolt hole cylinder   {bolt_hole.feature_id}")

    # ── 3. Subtract the single hole from the plate ───────────────────────
    plate.cut(bolt_hole, name="FirstHoleCut")
    print(f"✅ First hole cut       {plate.feature_id}")

    # ── 4. Repeat the hole along the plate length ────────────────────────
    # Spacing = total available span divided equally between holes.
    spacing = PLATE_LENGTH / HOLE_COUNT
    plate.linear_pattern(
        direction=(1.0, 0.0, 0.0),
        count=HOLE_COUNT,
        spacing=spacing,
        name="BoltHolePattern",
    )
    print(f"✅ Bolt hole pattern    {plate.feature_id}")

    # ── 5. Round the long edges of the plate ────────────────────────────
    plate.fillet(edges="top", radius=FILLET_R, name="EdgeFillet")
    print(f"✅ Edge fillet          {plate.feature_id}")

    # ── 6. Inspect the feature tree ─────────────────────────────────────
    ctx = get_default_context()
    node_count = len(ctx.tree.nodes)
    print(f"\nFeature tree: {node_count} nodes")
    for node in ctx.tree.nodes.values():
        deps = ", ".join(node.depends_on) if node.depends_on else "—"
        print(f"  [{node.status:>10}]  {node.id:12}  {node.operation:20}  deps=[{deps}]")

    # ── 7. Write tree JSON for inspection / replay ────────────────────────
    json_path = Path(tempfile.gettempdir()) / "bracket_tree.json"
    json_path.write_text(json.dumps(ctx.tree.model_dump(), indent=2))
    print(f"\n✅ Tree JSON → {json_path}")

    # ── 8. Export the finished part to STEP ──────────────────────────────
    step_path = Path(tempfile.gettempdir()) / "bracket.step"
    plate.export(str(step_path))
    print(f"✅ STEP export → {step_path}")


if __name__ == "__main__":
    main()
