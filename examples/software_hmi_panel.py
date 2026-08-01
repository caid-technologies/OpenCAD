"""Software example: operator panel for a display, buttons, and encoder access."""

from opencad import Part, Sketch


panel_profile = (
    Sketch(name="HMI Panel Profile")
    .rect(120, 70)
    .circle(6, center=(20, 18), subtract=True)
    .circle(6, center=(40, 18), subtract=True)
    .circle(6, center=(60, 18), subtract=True)
    .circle(6, center=(80, 18), subtract=True)
    .circle(6, center=(100, 18), subtract=True)
    .circle(9, center=(104, 50), subtract=True)
    .circle(3, center=(12, 58), subtract=True)
    .circle(3, center=(108, 58), subtract=True)
)

Part(name="HMI Panel").extrude(panel_profile, depth=3, name="Panel Blank")
