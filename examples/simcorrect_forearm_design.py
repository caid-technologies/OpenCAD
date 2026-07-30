from __future__ import annotations

from pathlib import Path

from opencad import Part, Sketch


def build_forearm_artifact(path: str | Path = "caid-design.json") -> Path:
    sketch = Sketch(name="Forearm profile").rect(30, 4)
    part = Part(name="forearm").extrude(sketch, depth=4, name="Forearm body")
    part.export_design_artifact(
        str(path),
        artifact_id="simcorrect-problem1-forearm",
        parameters={
            "forearm_length": {
                "value": 0.30,
                "unit": "m",
                "role": "geometry",
                "feature_id": part.feature_id,
            }
        },
        simulation_tags=[
            {"name": "right_forearm", "kind": "body", "target": "r_forearm"},
            {"name": "forearm_length", "kind": "parameter", "target": "link2_length"},
        ],
    )
    return Path(path)


if __name__ == "__main__":
    build_forearm_artifact()
