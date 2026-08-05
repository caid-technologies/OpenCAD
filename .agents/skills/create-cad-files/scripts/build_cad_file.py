#!/usr/bin/env python3
"""Build an OpenCAD Python model and atomically publish validated CAD output."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from validate_cad_file import inspect_cad_file


SUPPORTED_SUFFIXES = {".step", ".stp", ".stl"}


def _temporary_path(destination: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}-",
        suffix=destination.suffix,
        dir=destination.parent,
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def build_cad_file(
    model: str | Path,
    output: str | Path,
    *,
    tree_output: str | Path | None = None,
    force: bool = False,
) -> dict[str, object]:
    model_path = Path(model).resolve()
    output_path = Path(output).resolve()
    tree_path = Path(tree_output).resolve() if tree_output else None

    if not model_path.is_file():
        raise ValueError(f"Model script does not exist: {model_path}")
    if model_path.suffix.lower() != ".py":
        raise ValueError("The OpenCAD model must be a .py file.")
    if output_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Output must end in .step, .stp, or .stl.")
    if tree_path == output_path:
        raise ValueError("CAD output and feature-tree output must use different paths.")
    for destination in (output_path, tree_path):
        if destination is not None and destination.exists() and not force:
            raise FileExistsError(f"Refusing to replace existing file without --force: {destination}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if tree_path is not None:
        tree_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = _temporary_path(output_path)
    temporary_tree = _temporary_path(tree_path) if tree_path is not None else None

    try:
        try:
            from opencad.cli import main as opencad_main
            from opencad.runtime import get_default_context
        except ImportError as exc:
            raise RuntimeError(
                'OpenCAD with OCCT is required. Install it with: pip install "opencad[occt]"'
            ) from exc

        arguments = [
            "run",
            str(model_path),
            "--export",
            str(temporary_output),
            "--backend",
            "occt",
        ]
        if temporary_tree is not None:
            arguments.extend(["--tree-output", str(temporary_tree)])
        exit_code = opencad_main(arguments)
        if exit_code != 0:
            raise RuntimeError(f"OpenCAD exited with status {exit_code}.")

        summary = inspect_cad_file(temporary_output)
        summary["features"] = len(get_default_context().tree.nodes) - 1
        os.replace(temporary_output, output_path)
        summary["path"] = str(output_path)
        if tree_path is not None and temporary_tree is not None:
            os.replace(temporary_tree, tree_path)
            summary["tree_path"] = str(tree_path)
        summary["model_path"] = str(model_path)
        return summary
    finally:
        temporary_output.unlink(missing_ok=True)
        if temporary_tree is not None:
            temporary_tree.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and validate an OpenCAD STEP or STL file")
    parser.add_argument("model", help="OpenCAD Python model")
    parser.add_argument("output", help="Destination ending in .step, .stp, or .stl")
    parser.add_argument("--tree-output", help="Optional feature-tree JSON destination")
    parser.add_argument("--force", action="store_true", help="Replace existing output files")
    args = parser.parse_args(argv)
    summary = build_cad_file(
        args.model,
        args.output,
        tree_output=args.tree_output,
        force=args.force,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
