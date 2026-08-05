from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from opencad.cli import main

HAS_OCCT = (
    importlib.util.find_spec("cadquery") is not None
    and importlib.util.find_spec("OCP") is not None
)


@pytest.mark.parametrize(
    ("script_name", "expected_operations"),
    [
        pytest.param(
            "hardware_mounting_bracket.py",
            ["create_sketch", "extrude", "fillet_edges"],
            id="hardware-mounting-bracket",
        ),
        pytest.param(
            "hardware_pcb_carrier.py",
            ["create_sketch", "extrude", "offset_shape"],
            id="hardware-pcb-carrier",
        ),
        pytest.param(
            "software_hmi_panel.py",
            ["create_sketch", "extrude"],
            id="software-hmi-panel",
        ),
        pytest.param(
            "firmware_programmer_fixture.py",
            ["create_sketch", "extrude"],
            id="firmware-programmer-fixture",
        ),
        pytest.param(
            "full_device_cable_grommet.py",
            ["create_cylinder", "create_cylinder", "boolean_cut"],
            id="full-device-cable-grommet",
        ),
    ],
)
def test_examples_run_export_and_tree(
    tmp_path: Path,
    examples_dir: Path,
    script_name: str,
    expected_operations: list[str],
) -> None:
    step_path = tmp_path / f"{Path(script_name).stem}.step"
    tree_path = tmp_path / f"{Path(script_name).stem}.json"

    arguments = [
        "run",
        str(examples_dir / script_name),
        "--tree-output",
        str(tree_path),
    ]
    if HAS_OCCT:
        arguments.extend(["--export", str(step_path)])
    else:
        arguments.extend(["--backend", "analytic"])

    code = main(arguments)

    assert code == 0
    if HAS_OCCT:
        assert step_path.read_text(encoding="utf-8").startswith("ISO-10303-21;")
    assert tree_path.exists()

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    assert tree["root_id"] == "root"

    operations = [
        node["operation"]
        for node_id, node in tree["nodes"].items()
        if node_id != tree["root_id"]
    ]
    assert operations == expected_operations
    assert all(node["status"] == "built" for node in tree["nodes"].values())
