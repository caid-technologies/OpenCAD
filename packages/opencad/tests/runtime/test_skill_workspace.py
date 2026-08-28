from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import UUID


def _load_project_allocator():
    scripts_dir = Path(__file__).resolve().parents[4] / "skills" / "create-cad-files" / "scripts"
    spec = importlib.util.spec_from_file_location(
        "create_cad_project",
        scripts_dir / "create_project.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_project_allocator_uses_a_generated_uuid_under_the_workspace(tmp_path: Path) -> None:
    allocator = _load_project_allocator()
    workspace = tmp_path / "forma-workspace"

    project_path = allocator.create_project_directory(workspace)

    assert project_path.parent == workspace
    UUID(project_path.name)
    assert project_path.is_dir()


def test_project_allocator_creates_unique_directories(tmp_path: Path) -> None:
    allocator = _load_project_allocator()
    workspace = tmp_path / "forma-workspace"

    project_paths = {
        allocator.create_project_directory(workspace)
        for _ in range(2)
    }

    assert len(project_paths) == 2
