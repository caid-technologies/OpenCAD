#!/usr/bin/env python3
"""Create a unique project directory in the shared Forma workspace."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path


WORKSPACE_NAME = "forma-workspace"


def create_project_directory(workspace: str | Path | None = None) -> Path:
    """Create and return a UUID-named project directory."""
    workspace_path = (
        Path(workspace).expanduser()
        if workspace is not None
        else Path.home() / WORKSPACE_NAME
    )
    workspace_path.mkdir(parents=True, exist_ok=True)

    while True:
        project_path = workspace_path / str(uuid.uuid4())
        try:
            project_path.mkdir()
        except FileExistsError:
            continue
        return project_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Forma workspace project directory")
    parser.add_argument(
        "--workspace",
        help="Workspace root override for tests or isolated environments",
    )
    args = parser.parse_args(argv)
    print(create_project_directory(args.workspace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
