from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_builder():
    scripts_dir = Path(__file__).resolve().parents[4] / "skills" / "create-cad-files" / "scripts"
    spec = importlib.util.spec_from_file_location("create_cad_file_builder", scripts_dir / "build_cad_file.py")
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(scripts_dir))
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(scripts_dir))


def test_build_helper_supports_sibling_modules(tmp_path: Path) -> None:
    if importlib.util.find_spec("cadquery") is None or importlib.util.find_spec("OCP") is None:
        pytest.skip("OCCT is not installed")

    components_path = tmp_path / "components.py"
    assembly_path = tmp_path / "assembly.py"
    output_path = tmp_path / "assembly.step"
    components_path.write_text(
        "from opencad import Part\n\n"
        "def make_base():\n"
        "    return Part(name='Base').box(10, 10, 2)\n",
        encoding="utf-8",
    )
    assembly_path.write_text(
        "from components import make_base\n\n"
        "result = make_base()\n",
        encoding="utf-8",
    )

    builder = _load_builder()
    summary = builder.build_cad_file(assembly_path, output_path)

    assert summary["model_path"] == str(assembly_path.resolve())
    assert output_path.exists()
