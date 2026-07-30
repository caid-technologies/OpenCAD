"""Full-device example: cable grommet built from concentric cylindrical primitives."""

from opencad import Part


outer = Part(name="Outer Grommet").cylinder(14, 10, name="Outer Cylinder")
inner = Part(name="Inner Clearance").cylinder(8, 10, name="Inner Cylinder")

outer.cut(inner, name="Cable Passage")
