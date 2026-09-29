# OpenCAD modeling reference

OpenCAD dimensions are unitless; use millimeters consistently for mechanical parts.

## Basic model

```python
from opencad import Part, Sketch

WIDTH = 80.0
HEIGHT = 30.0
THICKNESS = 4.0
HOLE_RADIUS = 3.0

profile = (
    Sketch(name="Plate profile")
    .rect(WIDTH, HEIGHT)
    .circle(HOLE_RADIUS, center=(8.0, 8.0), subtract=True)
    .circle(HOLE_RADIUS, center=(72.0, 8.0), subtract=True)
)

result = Part(name="Plate").extrude(profile, depth=THICKNESS, name="Plate body")
result.fillet(edges="top", radius=0.75, name="Edge relief")
```

The build helper exports the runtime's last generated shape. Ensure the final operation belongs to the intended result.

## Sketches

- `Sketch(name=..., plane="XY", origin=(x, y, z))`
- `.rect(width, height, origin=(x, y))`
- `.circle(radius, center=(x, y), subtract=False)`
- `.line((x1, y1), (x2, y2))`

Build arbitrary planar profiles from consecutive lines and close the final point back to the first. Keep open line/arc paths for sweeps; solid extrusions require a closed, non-self-intersecting profile.

Use `circle(..., subtract=True)` only for holes strictly inside an outer profile. Leave clearance from the boundary and other holes: touching, overlapping, or crossing loops are invalid. For example, on `rect(90, 40)`, a radius-3 circle centered at `(87, 20)` touches the right edge, and one centered at `(90, 20)` crosses it. Neither is an interior sketch hole.

`rect()` does not accept `subtract=True`. For rectangular cutouts, extrude a separate rectangular tool and subtract it with `.cut()`. Use the same solid-boolean approach for circular edge notches:

```python
plate = Part(name="Plate").extrude(Sketch().rect(90, 40), depth=5)
notch = Part(name="Edge notch tool").extrude(
    Sketch().circle(3, center=(90, 20)), depth=5,
)
plate.cut(notch, name="Edge notch")
slot = Part(name="Slot tool").extrude(
    Sketch().rect(10, 4, origin=(20, 18)), depth=5,
)
plate.cut(slot, name="Rectangular slot")
```

## Solids and features

- `Part(name=...).box(length, width, height)`
- `.cylinder(radius, height)`
- `.sphere(radius)`
- `.cone(radius1, radius2, height)`
- `.torus(major_radius, minor_radius)`
- `.translate((dx, dy, dz))`
- `.extrude(sketch, depth=value, both=False)`
- `.union(other)`, `.cut(other)`, `.intersect(other)`
- `.fillet(edges="all" | "top" | [edge_ids], radius=value)`
- `.chamfer(edges="all" | "top" | [edge_ids], distance=value)`
- `.offset(distance)`
- `.mirror(plane_origin=(...), plane_normal=(...))`
- `.linear_pattern(direction=(...), count=n, spacing=value)`
- `.circular_pattern(axis_origin=(...), axis_direction=(...), count=n, angle=360)`

Boxes are centered at the modeling origin in both backends. For example, `Part().box(10, 5, 3)` spans approximately `(-5, -2.5, -1.5)` to `(5, 2.5, 1.5)`. Use `.translate((dx, dy, dz))` to position a completed 3-D primitive or other active shape. The operation creates a new positioned feature while preserving the fluent `Part` handle. For booleans, create the target, create the tool, position either shape as needed, then make the target's boolean operation the final call:

```python
outer = Part(name="Outer").cylinder(14.0, 10.0)
inner = Part(name="Clearance").cylinder(8.0, 10.0)
inner.translate((0.0, 0.0, 2.0))
outer.cut(inner, name="Bore")
```

## Output conventions

- `.step` or `.stp`: native B-rep exchange geometry.
- `.stl`: tessellated mesh; dimensions remain in the chosen unit convention but STL does not encode a unit.
- `*.tree.json`: rebuildable OpenCAD feature history created by the build helper.
