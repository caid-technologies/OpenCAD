"""Round-base spray-bottle concept model with integrated trigger and nozzle."""

from opencad import Part, Sketch


BODY_RADIUS = 36.0
BODY_HEIGHT = 145.0
NECK_RADIUS = 14.0
NECK_START_Z = 137.0
NECK_HEIGHT = 42.0
COLLAR_RADIUS = 19.0
COLLAR_START_Z = 156.0
COLLAR_HEIGHT = 14.0
HEAD_START_Z = 170.0
HEAD_HEIGHT = 24.0
TRIGGER_START_Z = 144.0
TRIGGER_HEIGHT = 31.0

# Extruding a circular sketch upward from Z=0 creates a true round base.
body_profile = Sketch(name="Circular reservoir profile").circle(BODY_RADIUS)
bottle = Part(name="Round Reservoir").extrude(
    body_profile,
    depth=BODY_HEIGHT,
    name="Circular Bottle Body",
)

neck_profile = Sketch(
    name="Neck profile",
    origin=(0.0, 0.0, NECK_START_Z),
).circle(NECK_RADIUS)
neck = Part(name="Bottle Neck").extrude(
    neck_profile,
    depth=NECK_HEIGHT,
    name="Raised Neck",
)
bottle.union(neck, name="Body and Neck")

collar_profile = Sketch(
    name="Pump collar profile",
    origin=(0.0, 0.0, COLLAR_START_Z),
).circle(COLLAR_RADIUS)
collar = Part(name="Pump Collar").extrude(
    collar_profile,
    depth=COLLAR_HEIGHT,
    name="Pump Collar",
)
bottle.union(collar, name="Bottle with Collar")

head_profile = (
    Sketch(name="Sprayer head profile", origin=(0.0, 0.0, HEAD_START_Z))
    .line((-20.0, -15.0), (28.0, -15.0))
    .line((28.0, -15.0), (38.0, -10.0))
    .line((38.0, -10.0), (68.0, -8.0))
    .line((68.0, -8.0), (75.0, -5.0))
    .line((75.0, -5.0), (75.0, 5.0))
    .line((75.0, 5.0), (68.0, 8.0))
    .line((68.0, 8.0), (38.0, 10.0))
    .line((38.0, 10.0), (28.0, 15.0))
    .line((28.0, 15.0), (-20.0, 15.0))
    .line((-20.0, 15.0), (-24.0, 10.0))
    .line((-24.0, 10.0), (-24.0, -10.0))
    .line((-24.0, -10.0), (-20.0, -15.0))
)
head = Part(name="Sprayer Head").extrude(
    head_profile,
    depth=HEAD_HEIGHT,
    name="Head and Nozzle",
)
bottle.union(head, name="Bottle with Sprayer Head")

trigger_profile = (
    Sketch(name="Trigger profile", origin=(0.0, 0.0, TRIGGER_START_Z))
    .line((8.0, -12.0), (28.0, -10.0))
    .line((28.0, -10.0), (31.0, -6.0))
    .line((31.0, -6.0), (31.0, 6.0))
    .line((31.0, 6.0), (28.0, 10.0))
    .line((28.0, 10.0), (8.0, 12.0))
    .line((8.0, 12.0), (5.0, 7.0))
    .line((5.0, 7.0), (5.0, -7.0))
    .line((5.0, -7.0), (8.0, -12.0))
)
trigger = Part(name="Trigger").extrude(
    trigger_profile,
    depth=TRIGGER_HEIGHT,
    name="Trigger Lever",
)

bottle.union(trigger, name="Complete Round-Base Spray Bottle")
