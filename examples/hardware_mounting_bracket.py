"""Hardware example: mounting bracket with corner fasteners and a cable pass-through."""

from opencad import Part, Sketch


bracket_profile = (
    Sketch(name="Bracket Profile")
    .rect(80, 30)
    .circle(3, center=(8, 8), subtract=True)
    .circle(3, center=(72, 8), subtract=True)
    .circle(3, center=(8, 22), subtract=True)
    .circle(3, center=(72, 22), subtract=True)
    .circle(5, center=(40, 15), subtract=True)
)

Part(name="Mounting Bracket").extrude(
    bracket_profile,
    depth=4,
    name="Bracket Body",
).fillet(edges="top", radius=0.75, name="Bracket Edge Relief")
