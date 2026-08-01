"""Firmware example: fixture plate for programming headers and alignment pins."""

from opencad import Part, Sketch


fixture_profile = (
    Sketch(name="Programmer Fixture Profile")
    .rect(70, 40)
    .circle(2.5, center=(10, 10), subtract=True)
    .circle(2.5, center=(60, 10), subtract=True)
    .circle(2.5, center=(10, 30), subtract=True)
    .circle(2.5, center=(60, 30), subtract=True)
    .circle(4, center=(25, 20), subtract=True)
    .circle(4, center=(35, 20), subtract=True)
    .circle(4, center=(45, 20), subtract=True)
)

Part(name="Programmer Fixture").extrude(
    fixture_profile,
    depth=5,
    name="Fixture Plate",
)
