from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from opencad_tree.models import FeatureTree


def build_system_prompt(tree_state: FeatureTree) -> str:
    tree_json = json.dumps(tree_state.model_dump(), indent=2, sort_keys=True)
    return (
        "OpenCAD Agent System Prompt\n"
        "\n"
        "Current feature tree state (JSON):\n"
        f"{tree_json}\n"
        "\n"
        "Available operations and their schemas:\n"
        f"{_API_REFERENCE}\n"
        "\n"
        "Parametric features:\n"
        "- Nodes may have typed_parameters and parameter_bindings.\n"
        "- Bindings can include an 'expression' field for computed values.\n"
        "- Suppressed nodes (and their descendants) are transitively suppressed.\n"
        "\n"
        "Instruction: always name features descriptively.\n"
        "Instruction: verify shapes exist and are not suppressed before referencing them.\n"
        "Instruction: plan the full sequence before executing.\n"
    )


@lru_cache(maxsize=1)
def _load_example_scripts() -> str:
    examples_dir = Path(__file__).resolve().parents[3] / "examples"
    example_files = [
        "hardware_mounting_bracket.py",
        "hardware_pcb_carrier.py",
        "software_hmi_panel.py",
    ]
    snippets: list[str] = []
    for filename in example_files:
        path = examples_dir / filename
        if not path.exists():
            continue
        snippet = path.read_text(encoding="utf-8").strip()
        snippets.append(f"examples/{filename}:\n```python\n{snippet}\n```")
    return "\n\n".join(snippets)


_API_REFERENCE = """\
Sketch methods (all return self for chaining):
  Sketch(name=str, plane="XY", origin=(x,y,z))      # all constructor arguments are keyword-only
  .line(start=(x,y), end=(x,y))
  .rect(width, height, *, origin=(x,y))
  .circle(radius, *, center=(x,y))                  # one closed profile per sketch

Part methods (all return self for chaining):
  Part(name=str)                                     # constructor argument is keyword-only
  .box(length, width, height, *, name=str)
  .cylinder(radius, height, *, name=str)
  .sphere(radius, *, name=str)
  .cone(radius1, radius2, height, *, name=str)
  .torus(major_radius, minor_radius, *, name=str)
  .extrude(sketch, *, depth, both=False, name=str)   # sketch is a Sketch instance, NO subtract arg
  .union(other_part, *, name=str)
  .cut(other_part, *, name=str)
  .intersect(other_part, *, name=str)
  .fillet(*, edges=None|"all"|"top"|[id,...], radius, name=str)
  .chamfer(*, edges=None|"all"|"top"|[id,...], distance, name=str)
  .shell(*, face_ids=[id,...], thickness, name=str)
  .draft(*, face_ids=[id,...], angle, pull_direction=(x,y,z), name=str)
  .offset(distance, *, name=str)
  .linear_pattern(*, direction=(x,y,z), count, spacing, name=str)
  .circular_pattern(*, axis_origin=(x,y,z), axis_direction=(x,y,z), count, angle=360.0, name=str)
  .mirror(*, plane_origin=(x,y,z), plane_normal=(x,y,z), name=str)
"""


_COMPOSITION_EXAMPLE = """\
Valid repeated-feature composition example:
```python
from opencad import Part, Sketch

core = Part(name="Pattern Core").cylinder(radius=20, height=6, name="Core")
feature_profile = Sketch(name="Radial Feature").rect(6, 6, origin=(18, -3))
feature = Part(name="Feature").extrude(feature_profile, depth=6, name="Feature Body")
features = feature.circular_pattern(
    axis_origin=(0, 0, 0),
    axis_direction=(0, 0, 1),
    count=12,
    angle=360,
    name="Radial Pattern",
)
combined = core.union(features, name="Combined Body")
opening = Part(name="Opening").cylinder(radius=5, height=6, name="Opening Tool")
result = combined.cut(opening, name="Finished Part")
```
"""


def build_code_generation_prompt(tree_state: FeatureTree) -> str:
    base_prompt = build_system_prompt(tree_state)
    examples = _load_example_scripts()
    return (
        f"{base_prompt}\n"
        "Generate OpenCAD Python code that matches the concise fluent style used in the repository examples.\n"
        "Requirements:\n"
        "- Return only valid Python code.\n"
        "- Use `from opencad import Part, Sketch`.\n"
        "- Prefer a named sketch variable followed by a named Part fluent chain.\n"
        "- Use descriptive names for sketches, parts, and operations.\n"
        "- Keep the script self-contained and aligned with the examples below.\n"
        "- Do not use filesystem, network, subprocess, dynamic execution, functions, classes, loops, or imports other than `from opencad import Part, Sketch`.\n"
        "- Do not enclose the returned code with comment markers, or markers saying it's python, assume that the code is executed.\n"
        "- Constructors are keyword-only: always write `Part(name=...)` and pass only named arguments to `Sketch(...)`.\n"
        "- Prefer `Sketch(name=...)`; if origin is supplied it must be a 3-number tuple, while rect origin and circle center use 2-number tuples.\n"
        "- Create each independent solid from its own Part instance; do not call an operation on a Part that has no shape.\n"
        "- Use the native box, cylinder, sphere, cone, or torus Part method whenever that primitive is requested; do not approximate it with a sketch and extrusion.\n"
        "- A torus must use `Part(name=...).torus(major_radius=..., minor_radius=..., name=...)`.\n"
        "- For radial repetition, sketch one feature away from the axis, extrude it, then use circular_pattern and union it with the core.\n"
        "- For a cog or gear, make each tooth cross the core's outside radius so it visibly protrudes; do not put a hole in the tooth profile.\n"
        "- Create holes as separate solid tools and subtract them with cut.\n"
        "- Never use `subtract=True` in a Sketch; the live kernel requires a separate solid tool and cut.\n"
        "- Each Sketch variable may call exactly one `rect` or exactly one `circle`, never both and never twice.\n"
        "\n"
        "API reference (use ONLY these signatures — do not invent parameters):\n"
        f"{_API_REFERENCE}\n"
        f"{_COMPOSITION_EXAMPLE}\n"
        "Reference examples:\n"
        f"{examples}\n"
    )
