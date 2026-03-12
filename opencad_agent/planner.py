from __future__ import annotations

import re
from typing import Any, Callable

from opencad_agent.models import OperationExecution
from opencad_agent.tools import ToolRuntime


def _parse_cube_dimensions(message: str) -> tuple[float, float, float] | None:
    """Extract cube/box dimensions from a user message.

    Supports formats like:
    - "30x30x30 mm" or "30x30x30mm"
    - "30 mm cube" or "30mm cube"
    - "cube of 30 mm" or "cube of 30mm"
    - "box 10x20x30"

    Returns (length, width, height) or None if not found.
    """
    lowered = message.lower()

    # Pattern: NxNxN (e.g., "30x30x30 mm")
    match = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", lowered)
    if match:
        return float(match.group(1)), float(match.group(2)), float(match.group(3))

    # Pattern: N mm cube or Nmm cube (uniform cube)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*cube", lowered)
    if match:
        size = float(match.group(1))
        return size, size, size

    # Pattern: cube of N mm or cube of Nmm
    match = re.search(r"cube\s+of\s+(\d+(?:\.\d+)?)", lowered)
    if match:
        size = float(match.group(1))
        return size, size, size

    return None


class OpenCadPlanner:
    def execute(self, message: str, runtime: ToolRuntime, reasoning: bool = False) -> tuple[str, list[OperationExecution]]:
        lowered = message.lower()

        if "mounting bracket" in lowered and "standoff" in lowered:
            operations = self._build_mounting_bracket(runtime)
            if reasoning:
                response = (
                    "Plan: base sketch -> base extrude -> 4 standoffs -> center cutout tool -> counterbore tool "
                    "-> two boolean cuts -> edge fillet. Executed operations in that order with validated IDs."
                )
            else:
                response = "Mounting bracket feature sequence generated and executed."
            return response, operations

        # Handle cube/box requests with dimension parsing
        if "cube" in lowered or "box" in lowered:
            dims = _parse_cube_dimensions(message)
            if dims:
                length, width, height = dims
                operations = self._build_box(runtime, length, width, height)
                if reasoning:
                    response = f"Plan: create {length}x{width}x{height} box via sketch and extrude. Sequence executed."
                else:
                    response = f"Created a {length}x{width}x{height} box."
                return response, operations

        operations = self._build_simple_feature(runtime)
        response = "Executed a minimal sketch-to-extrude sequence for the request."
        if reasoning:
            response = "Plan: create sketch then extrude. Sequence executed with dependency-safe IDs."
        return response, operations

    def _safe_call(
        self,
        operations: list[OperationExecution],
        tool: str,
        arguments: dict[str, Any],
        invoke: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            result = invoke()
            operations.append(OperationExecution(tool=tool, status="ok", arguments=arguments, result=result))
            return result
        except Exception as exc:  # pragma: no cover
            error = {"error": str(exc)}
            operations.append(OperationExecution(tool=tool, status="error", arguments=arguments, result=error))
            raise

    def _build_box(self, runtime: ToolRuntime, length: float, width: float, height: float) -> list[OperationExecution]:
        """Build a box/cube with the specified dimensions via sketch + extrude."""
        operations: list[OperationExecution] = []

        box_sketch_args = {
            "name": "Box Base Sketch",
            "entities": {
                "l1": {"id": "l1", "type": "line", "start": (0.0, 0.0), "end": (length, 0.0)},
                "l2": {"id": "l2", "type": "line", "start": (length, 0.0), "end": (length, width)},
                "l3": {"id": "l3", "type": "line", "start": (length, width), "end": (0.0, width)},
                "l4": {"id": "l4", "type": "line", "start": (0.0, width), "end": (0.0, 0.0)},
            },
            "profile_order": ["l1", "l2", "l3", "l4"],
            "constraints": [
                {"id": "d1", "type": "distance", "a": "l1", "value": length},
                {"id": "d2", "type": "distance", "a": "l2", "value": width},
            ],
        }

        sketch = self._safe_call(
            operations,
            "add_sketch",
            box_sketch_args,
            lambda: {"sketch_id": runtime.add_sketch(**box_sketch_args)},
        )
        sketch_id = str(sketch["sketch_id"])

        extrude_args = {"sketch_id": sketch_id, "depth": height, "name": "Box Extrude"}
        self._safe_call(
            operations,
            "extrude",
            extrude_args,
            lambda: {"feature_id": runtime.extrude(**extrude_args)},
        )

        return operations

    def _build_simple_feature(self, runtime: ToolRuntime) -> list[OperationExecution]:
        operations: list[OperationExecution] = []

        base_sketch_args = {
            "name": "Simple Base Sketch",
            "entities": {
                "l1": {"id": "l1", "type": "line", "start": (0.0, 0.0), "end": (30.0, 0.0)},
                "l2": {"id": "l2", "type": "line", "start": (30.0, 0.0), "end": (30.0, 20.0)},
                "l3": {"id": "l3", "type": "line", "start": (30.0, 20.0), "end": (0.0, 20.0)},
                "l4": {"id": "l4", "type": "line", "start": (0.0, 20.0), "end": (0.0, 0.0)},
            },
            "profile_order": ["l1", "l2", "l3", "l4"],
            "constraints": [{"id": "d1", "type": "distance", "a": "l1", "value": 30.0}],
        }

        sketch = self._safe_call(
            operations,
            "add_sketch",
            base_sketch_args,
            lambda: {"sketch_id": runtime.add_sketch(**base_sketch_args)},
        )
        sketch_id = str(sketch["sketch_id"])

        extrude_args = {"sketch_id": sketch_id, "depth": 8.0, "name": "Simple Extrude"}
        self._safe_call(
            operations,
            "extrude",
            extrude_args,
            lambda: {"feature_id": runtime.extrude(**extrude_args)},
        )

        return operations

    def _build_mounting_bracket(self, runtime: ToolRuntime) -> list[OperationExecution]:
        operations: list[OperationExecution] = []

        base_sketch_args = {
            "name": "Bracket Base Profile",
            "entities": {
                "l1": {"id": "l1", "type": "line", "start": (0.0, 0.0), "end": (80.0, 0.0)},
                "l2": {"id": "l2", "type": "line", "start": (80.0, 0.0), "end": (80.0, 50.0)},
                "l3": {"id": "l3", "type": "line", "start": (80.0, 50.0), "end": (0.0, 50.0)},
                "l4": {"id": "l4", "type": "line", "start": (0.0, 50.0), "end": (0.0, 0.0)},
            },
            "profile_order": ["l1", "l2", "l3", "l4"],
            "constraints": [
                {"id": "h1", "type": "horizontal", "a": "l1"},
                {"id": "v1", "type": "vertical", "a": "l2"},
                {"id": "d1", "type": "distance", "a": "l1", "value": 80.0},
                {"id": "d2", "type": "distance", "a": "l2", "value": 50.0},
            ],
        }
        sketch_result = self._safe_call(
            operations,
            "add_sketch",
            base_sketch_args,
            lambda: {"sketch_id": runtime.add_sketch(**base_sketch_args)},
        )
        base_sketch_id = str(sketch_result["sketch_id"])

        extrude_args = {"sketch_id": base_sketch_id, "depth": 10.0, "name": "Bracket Base"}
        base_result = self._safe_call(
            operations,
            "extrude",
            extrude_args,
            lambda: {"feature_id": runtime.extrude(**extrude_args)},
        )
        base_feature_id = str(base_result["feature_id"])

        standoff_specs = [
            ({"x": 10.0, "y": 10.0, "z": 10.0}, "Standoff Front Left"),
            ({"x": 70.0, "y": 10.0, "z": 10.0}, "Standoff Front Right"),
            ({"x": 10.0, "y": 40.0, "z": 10.0}, "Standoff Rear Left"),
            ({"x": 70.0, "y": 40.0, "z": 10.0}, "Standoff Rear Right"),
        ]

        for position, name in standoff_specs:
            cyl_args = {"position": position, "radius": 4.0, "height": 14.0, "name": name}
            self._safe_call(
                operations,
                "add_cylinder",
                cyl_args,
                lambda cyl_args=cyl_args: {"feature_id": runtime.add_cylinder(**cyl_args)},
            )

        cutout_sketch_args = {
            "name": "Center Cutout Sketch",
            "entities": {
                "c1": {"id": "c1", "type": "circle", "cx": 40.0, "cy": 25.0, "radius": 12.0}
            },
            "constraints": [],
        }
        cutout_sketch = self._safe_call(
            operations,
            "add_sketch",
            cutout_sketch_args,
            lambda: {"sketch_id": runtime.add_sketch(**cutout_sketch_args)},
        )
        cutout_sketch_id = str(cutout_sketch["sketch_id"])

        cutout_tool_args = {
            "sketch_id": cutout_sketch_id,
            "depth": 14.0,
            "name": "Center Cutout Tool",
        }
        cutout_tool = self._safe_call(
            operations,
            "extrude",
            cutout_tool_args,
            lambda: {"feature_id": runtime.extrude(**cutout_tool_args)},
        )
        cutout_tool_id = str(cutout_tool["feature_id"])

        cut_args = {"base_id": base_feature_id, "tool_id": cutout_tool_id, "name": "Central Cutout"}
        cut_result = self._safe_call(
            operations,
            "boolean_cut",
            cut_args,
            lambda: {"feature_id": runtime.boolean_cut(**cut_args)},
        )
        cut_feature_id = str(cut_result["feature_id"])

        ear_sketch_args = {
            "name": "Counterbore Ear Sketch",
            "entities": {
                "c1": {"id": "c1", "type": "circle", "cx": 6.0, "cy": 25.0, "radius": 3.5},
                "c2": {"id": "c2", "type": "circle", "cx": 74.0, "cy": 25.0, "radius": 3.5},
            },
            "constraints": [],
        }
        ear_sketch = self._safe_call(
            operations,
            "add_sketch",
            ear_sketch_args,
            lambda: {"sketch_id": runtime.add_sketch(**ear_sketch_args)},
        )
        ear_sketch_id = str(ear_sketch["sketch_id"])

        ear_tool_args = {"sketch_id": ear_sketch_id, "depth": 8.0, "name": "Counterbore Tool"}
        ear_tool = self._safe_call(
            operations,
            "extrude",
            ear_tool_args,
            lambda: {"feature_id": runtime.extrude(**ear_tool_args)},
        )
        ear_tool_id = str(ear_tool["feature_id"])

        ear_cut_args = {"base_id": cut_feature_id, "tool_id": ear_tool_id, "name": "Counterbored Mounting Ears"}
        ear_cut = self._safe_call(
            operations,
            "boolean_cut",
            ear_cut_args,
            lambda: {"feature_id": runtime.boolean_cut(**ear_cut_args)},
        )
        ear_cut_id = str(ear_cut["feature_id"])

        fillet_args = {
            "shape_id": ear_cut_id,
            "edge_selection": ["outer_perimeter"],
            "radius": 1.25,
            "name": "Edge Finish Fillet",
        }
        self._safe_call(
            operations,
            "fillet_edges",
            fillet_args,
            lambda: {"feature_id": runtime.fillet_edges(**fillet_args)},
        )

        return operations

    def generate_code(self, message: str) -> str:
        lowered = message.lower()
        if "mounting bracket" in lowered:
            return (
                '"""Generated OpenCAD example: mounting bracket with fastener holes."""\n\n'
                "from opencad import Part, Sketch\n\n\n"
                "bracket_profile = (\n"
                '    Sketch(name="Generated Bracket Profile")\n'
                "    .rect(80, 30)\n"
                "    .circle(3, center=(8, 8), subtract=True)\n"
                "    .circle(3, center=(72, 8), subtract=True)\n"
                "    .circle(3, center=(8, 22), subtract=True)\n"
                "    .circle(3, center=(72, 22), subtract=True)\n"
                "    .circle(5, center=(40, 15), subtract=True)\n"
                ")\n\n"
                'Part(name="Generated Mounting Bracket").extrude(\n'
                "    bracket_profile,\n"
                "    depth=4,\n"
                '    name="Bracket Body",\n'
                ').fillet(edges="top", radius=0.75, name="Bracket Edge Relief")\n'
            )

        if "pcb" in lowered or "carrier" in lowered:
            return (
                '"""Generated OpenCAD example: PCB carrier plate."""\n\n'
                "from opencad import Part, Sketch\n\n\n"
                "carrier_profile = (\n"
                '    Sketch(name="Generated PCB Carrier Profile")\n'
                "    .rect(90, 60)\n"
                "    .circle(2.2, center=(8, 8), subtract=True)\n"
                "    .circle(2.2, center=(82, 8), subtract=True)\n"
                "    .circle(2.2, center=(8, 52), subtract=True)\n"
                "    .circle(2.2, center=(82, 52), subtract=True)\n"
                "    .circle(7, center=(45, 30), subtract=True)\n"
                ")\n\n"
                'Part(name="Generated PCB Carrier").extrude(\n'
                "    carrier_profile,\n"
                "    depth=3,\n"
                '    name="Carrier Plate",\n'
                ').offset(0.4, name="Carrier Reinforcement")\n'
            )

        # Handle cube/box requests
        if "cube" in lowered or "box" in lowered:
            dims = _parse_cube_dimensions(message)
            if dims:
                length, width, height = dims
                # Check if it's a uniform cube
                if length == width == height:
                    return (
                        f'"""Generated OpenCAD example: {length}mm cube."""\n\n'
                        "from opencad import Part\n\n\n"
                        f'Part(name="Generated Cube").box({length}, {length}, {length}, name="Cube")\n'
                    )
                else:
                    return (
                        f'"""Generated OpenCAD example: {length}x{width}x{height} box."""\n\n'
                        "from opencad import Part\n\n\n"
                        f'Part(name="Generated Box").box({length}, {width}, {height}, name="Box")\n'
                    )

        return (
            '"""Generated OpenCAD example: simple extruded part."""\n\n'
            "from opencad import Part, Sketch\n\n\n"
            "part_profile = (\n"
            '    Sketch(name="Generated Profile")\n'
            "    .rect(30, 20)\n"
            "    .circle(4, center=(15, 10), subtract=True)\n"
            ")\n\n"
            'Part(name="Generated Part").extrude(part_profile, depth=8, name="Part Body")\n'
        )
