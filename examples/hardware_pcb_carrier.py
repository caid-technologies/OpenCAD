"""Hardware example: PCB carrier plate with mounting holes and a clearance opening."""

from opencad import Part, Sketch


carrier_profile = (
    Sketch(name="PCB Carrier Profile")
    .rect(90, 60)
    .circle(2.2, center=(8, 8), subtract=True)
    .circle(2.2, center=(82, 8), subtract=True)
    .circle(2.2, center=(8, 52), subtract=True)
    .circle(2.2, center=(82, 52), subtract=True)
    .circle(7, center=(45, 30), subtract=True)
)

Part(name="PCB Carrier").extrude(
    carrier_profile,
    depth=3,
    name="Carrier Plate",
).offset(0.4, name="Carrier Reinforcement")
