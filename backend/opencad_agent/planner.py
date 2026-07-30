from __future__ import annotations

from typing import Any, Callable

from opencad_agent.models import OperationExecution
from opencad_agent.tools import ToolRuntime


class UnsupportedPromptError(ValueError):
    """Raised when no deterministic planner or local code template matches a prompt."""


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

        raise UnsupportedPromptError(
            "Unsupported CAD request. The built-in planner only supports the mounting-bracket workflow. "
            "Enable Generate Code with a configured OPENCAD_LLM_MODEL for arbitrary requests."
        )

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
                '"""Mounting bracket with fastener holes and center cutout."""\n'
                "from opencad import Part, Sketch\n\n"
                'plate = Part(name="Plate").extrude(\n'
                '    Sketch(name="Plate Outline").rect(80, 30),\n'
                '    depth=4, name="Plate Body",\n'
                ")\n"
                'h1 = Part(name="Hole TL").extrude(Sketch(name="HTL").circle(3, center=(8, 22)), depth=4, name="HTL Body")\n'
                'h2 = Part(name="Hole TR").extrude(Sketch(name="HTR").circle(3, center=(72, 22)), depth=4, name="HTR Body")\n'
                'h3 = Part(name="Hole BL").extrude(Sketch(name="HBL").circle(3, center=(8, 8)), depth=4, name="HBL Body")\n'
                'h4 = Part(name="Hole BR").extrude(Sketch(name="HBR").circle(3, center=(72, 8)), depth=4, name="HBR Body")\n'
                'center = Part(name="Center").extrude(Sketch(name="C").circle(5, center=(40, 15)), depth=4, name="C Body")\n'
                "bracket = plate.cut(h1).cut(h2).cut(h3).cut(h4).cut(center)\n"
            )

        if "pcb" in lowered or "carrier" in lowered:
            return (
                '"""PCB carrier plate with mounting holes and cable passthrough."""\n'
                "from opencad import Part, Sketch\n\n"
                # Outer plate: 90x60, 3mm thick
                'plate = Part(name="Carrier Plate").extrude(\n'
                '    Sketch(name="Carrier Outline").rect(90, 60),\n'
                '    depth=3, name="Carrier Plate Body",\n'
                ")\n\n"
                # Four 2.2mm mounting holes at corners (4.4mm dia)\n'
                'm1 = Part(name="Mount BL").extrude(Sketch(name="MBL").circle(2.2, center=(8, 8)), depth=3, name="MBL Body")\n'
                'm2 = Part(name="Mount BR").extrude(Sketch(name="MBR").circle(2.2, center=(82, 8)), depth=3, name="MBR Body")\n'
                'm3 = Part(name="Mount TL").extrude(Sketch(name="MTL").circle(2.2, center=(8, 52)), depth=3, name="MTL Body")\n'
                'm4 = Part(name="Mount TR").extrude(Sketch(name="MTR").circle(2.2, center=(82, 52)), depth=3, name="MTR Body")\n\n'
                # Center 7mm cable passthrough (14mm dia)\n'
                'passthrough = Part(name="Cable Passthrough").extrude(\n'
                '    Sketch(name="Passthrough Profile").circle(7, center=(45, 30)),\n'
                '    depth=3, name="Passthrough Body",\n'
                ")\n\n"
                # Cut all holes, then offset for reinforcement\n'
                "carrier = (\n"
                '    plate.cut(m1, name="Cut Mount BL")\n'
                '         .cut(m2, name="Cut Mount BR")\n'
                '         .cut(m3, name="Cut Mount TL")\n'
                '         .cut(m4, name="Cut Mount TR")\n'
                '         .cut(passthrough, name="Cut Passthrough")\n'
                '         .offset(0.4, name="Carrier Reinforcement")\n'
                ")\n"
            )

        raise UnsupportedPromptError(
            "Unsupported code-generation request. The built-in generator only supports mounting brackets "
            "and PCB carriers. Configure OPENCAD_LLM_MODEL for arbitrary requests."
        )
