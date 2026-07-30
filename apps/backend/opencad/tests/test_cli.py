from __future__ import annotations

import json
from pathlib import Path

from opencad import Part, Sketch, get_default_context, reset_default_context
from opencad.cli import main


def test_cli_build_round_trip(tmp_path: Path) -> None:
    reset_default_context()
    sketch = Sketch().rect(6, 6)
    Part().extrude(sketch, depth=4)

    ctx = get_default_context()
    model_path = tmp_path / "model.json"
    built_path = tmp_path / "model.built.json"
    model_path.write_text(ctx.serialize_tree(), encoding="utf-8")

    code = main(["build", str(model_path), "--output", str(built_path)])

    assert code == 0
    assert built_path.exists()
    built = json.loads(built_path.read_text(encoding="utf-8"))
    assert built["root_id"] == "root"


def test_cli_run_export_and_tree(tmp_path: Path) -> None:
    script_path = tmp_path / "model.py"
    step_path = tmp_path / "result.step"
    tree_path = tmp_path / "result-tree.json"
    script_path.write_text(
        "from opencad import Part, Sketch\n"
        "sk = Sketch().rect(10, 20).circle(2)\n"
        "Part().extrude(sk, depth=5)\n",
        encoding="utf-8",
    )

    code = main([
        "run",
        str(script_path),
        "--export",
        str(step_path),
        "--tree-output",
        str(tree_path),
    ])

    assert code == 0
    assert step_path.exists()
    assert tree_path.exists()
