#!/usr/bin/env python3
"""Perform deterministic structural checks on STEP and STL artifacts."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any


def inspect_cad_file(filepath: str | Path) -> dict[str, Any]:
    path = Path(filepath)
    if not path.is_file():
        raise ValueError(f"CAD file does not exist: {path}")

    suffix = path.suffix.lower()
    data = path.read_bytes()
    if not data:
        raise ValueError(f"CAD file is empty: {path}")

    if suffix in {".step", ".stp"}:
        return _inspect_step(path, data)
    if suffix == ".stl":
        return _inspect_stl(path, data)
    raise ValueError("Unsupported CAD format. Use a .step, .stp, or .stl file.")


def _inspect_step(path: Path, data: bytes) -> dict[str, Any]:
    upper = data.upper()
    if not upper.lstrip().startswith(b"ISO-10303-21;"):
        raise ValueError("STEP validation failed: missing ISO-10303-21 header.")
    if b"END-ISO-10303-21;" not in upper:
        raise ValueError("STEP validation failed: missing end marker.")
    if b"DATA;" not in upper or b"ENDSEC;" not in upper:
        raise ValueError("STEP validation failed: missing exchange data section.")
    return {
        "format": "step",
        "path": str(path.resolve()),
        "bytes": len(data),
        "valid": True,
    }


def _inspect_stl(path: Path, data: bytes) -> dict[str, Any]:
    triangle_count = _binary_stl_triangle_count(data)
    encoding = "binary"
    if triangle_count is None:
        text = data.decode("utf-8", errors="replace").lower()
        if not text.lstrip().startswith("solid") or "endsolid" not in text:
            raise ValueError("STL validation failed: file is neither valid binary nor recognizable ASCII STL.")
        triangle_count = text.count("facet normal")
        encoding = "ascii"
    if triangle_count < 1:
        raise ValueError("STL validation failed: mesh contains no triangles.")
    return {
        "format": "stl",
        "encoding": encoding,
        "triangles": triangle_count,
        "path": str(path.resolve()),
        "bytes": len(data),
        "valid": True,
    }


def _binary_stl_triangle_count(data: bytes) -> int | None:
    if len(data) < 84:
        return None
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    return triangle_count if 84 + triangle_count * 50 == len(data) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a STEP, STP, or STL artifact")
    parser.add_argument("file", help="CAD artifact to validate")
    args = parser.parse_args(argv)
    print(json.dumps(inspect_cad_file(args.file), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
