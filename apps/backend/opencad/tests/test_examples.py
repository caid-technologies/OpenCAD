from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencad.cli import main


REPO_ROOT = Path(__file__).resolve().parents[4]
EXAMPLES_DIR = REPO_ROOT / "examples"


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
def test_examples_run_export_and_tree(tmp_path: Path, script_name: str, expected_operations: list[str]) -> None:
    step_path = tmp_path / f"{Path(script_name).stem}.step"
    tree_path = tmp_path / f"{Path(script_name).stem}.json"

    code = main([
        "run",
        str(EXAMPLES_DIR / script_name),
        "--export",
        str(step_path),
        "--tree-output",
        str(tree_path),
    ])

    assert code == 0
    assert step_path.exists()
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
