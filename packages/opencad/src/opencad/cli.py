from __future__ import annotations

import argparse
import runpy
from pathlib import Path

from opencad.runtime import RuntimeContext, get_default_context, set_default_context
from opencad.kernel.core.backend_factory import BackendUnavailableError, create_backend
from opencad.turntable import (
    DEFAULT_DEFLECTION,
    DEFAULT_FPS,
    DEFAULT_FRAMES,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    SUPPORTED_FORMATS,
    TurntableOptions,
    resolve_format,
)


def _add_backend_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "occt", "analytic"],
        help="Geometry backend (auto prefers OCCT; STEP/STL export requires OCCT)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opencad", description="OpenCAD headless CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Rebuild a feature tree JSON in-process")
    build_parser.add_argument("model", help="Input model JSON file")
    build_parser.add_argument("--output", help="Output JSON path")
    build_parser.add_argument("--continue-on-error", action="store_true", help="Continue rebuild after failed nodes")
    build_parser.add_argument(
        "--id-strategy",
        default="readable",
        choices=["readable", "uuid"],
        help="Shape ID strategy for rebuild-created shapes",
    )
    _add_backend_argument(build_parser)
    build_parser.set_defaults(func=_cmd_build)

    run_parser = subparsers.add_parser("run", help="Run a Python script with the opencad fluent API")
    run_parser.add_argument("script", help="Python script path")
    run_parser.add_argument("--export", help="Optional STEP, STP, or STL output path")
    run_parser.add_argument("--tree-output", help="Optional path to write resulting feature tree JSON")
    run_parser.add_argument(
        "--id-strategy",
        default="readable",
        choices=["readable", "uuid"],
        help="Shape ID strategy for script execution",
    )
    _add_turntable_arguments(run_parser)
    _add_backend_argument(run_parser)
    run_parser.set_defaults(func=_cmd_run)

    return parser


def _add_turntable_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--turntable",
        help="Optional rotating preview output path (.gif or .mp4); requires the OCCT backend",
    )
    parser.add_argument(
        "--turntable-format",
        choices=list(SUPPORTED_FORMATS),
        help="Override the turntable format inferred from the output extension",
    )
    parser.add_argument(
        "--turntable-frames",
        type=int,
        default=DEFAULT_FRAMES,
        help=f"Frames in one full revolution (default: {DEFAULT_FRAMES})",
    )
    parser.add_argument(
        "--turntable-fps",
        type=int,
        default=DEFAULT_FPS,
        help=f"Playback rate in frames per second (default: {DEFAULT_FPS})",
    )
    parser.add_argument(
        "--turntable-size",
        default=f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}",
        help=f"Frame size as WIDTHxHEIGHT (default: {DEFAULT_WIDTH}x{DEFAULT_HEIGHT})",
    )
    parser.add_argument(
        "--turntable-deflection",
        type=float,
        default=DEFAULT_DEFLECTION,
        help=f"Tessellation tolerance; lower is finer (default: {DEFAULT_DEFLECTION})",
    )


def _parse_size(value: str) -> tuple[int, int]:
    width, separator, height = value.lower().partition("x")
    if not separator or not width.strip().isdigit() or not height.strip().isdigit():
        raise ValueError(f"Invalid --turntable-size '{value}'. Use WIDTHxHEIGHT, for example 640x480.")
    return int(width), int(height)


def _turntable_options(args: argparse.Namespace) -> TurntableOptions:
    width, height = _parse_size(args.turntable_size)
    return TurntableOptions(
        frames=args.turntable_frames,
        fps=args.turntable_fps,
        width=width,
        height=height,
        deflection=args.turntable_deflection,
    )


def _cmd_build(args: argparse.Namespace) -> int:
    backend = create_backend(args.backend, id_strategy=args.id_strategy)
    context = RuntimeContext(id_strategy=args.id_strategy, backend=backend)
    context.load_tree_json(args.model)
    tree = context.rebuild_tree(continue_on_error=args.continue_on_error)

    output_path = args.output
    if not output_path:
        input_path = Path(args.model)
        output_path = str(input_path.with_suffix(".built.json"))

    context.save_tree_json(output_path)
    print(f"Rebuilt tree '{tree.root_id}' with {len(tree.nodes)} nodes -> {output_path}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    export_format = _export_format(args.export) if args.export else None

    # Resolve turntable settings before running the script so a bad extension
    # or size is reported immediately rather than after the model is built.
    turntable_format = resolve_format(args.turntable, args.turntable_format) if args.turntable else None
    turntable_options = _turntable_options(args) if args.turntable else None
    if args.turntable and args.backend == "analytic":
        raise BackendUnavailableError(
            "The analytic backend cannot tessellate geometry, so it cannot render a turntable. "
            "Use --backend occt and install it with: uv sync --extra occt"
        )

    backend = create_backend(
        args.backend,
        id_strategy=args.id_strategy,
        require_native=bool(args.export) or bool(args.turntable),
    )
    context = RuntimeContext(id_strategy=args.id_strategy, backend=backend)
    set_default_context(context)

    script_path = Path(args.script)
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    runpy.run_path(str(script_path), run_name="__main__")

    current = get_default_context()
    if args.export:
        if not current.last_shape_id:
            raise RuntimeError(f"No shape was produced by the script, cannot export {export_format.upper()}.")
        if export_format == "stl":
            current.export_stl(current.last_shape_id, args.export)
        else:
            current.export_step(current.last_shape_id, args.export)
        print(f"Exported {export_format.upper()} to {args.export}")

    if args.turntable:
        if not current.last_shape_id:
            raise RuntimeError("No shape was produced by the script, cannot render a turntable.")
        current.export_turntable(
            current.last_shape_id,
            args.turntable,
            fmt=turntable_format,
            options=turntable_options,
        )
        print(f"Rendered {turntable_format.upper()} turntable to {args.turntable}")

    if args.tree_output:
        current.save_tree_json(args.tree_output)
        print(f"Wrote tree JSON to {args.tree_output}")

    print(f"Script completed. Nodes: {len(current.tree.nodes)}")
    return 0


def _export_format(filepath: str) -> str:
    suffix = Path(filepath).suffix.lower()
    if suffix in {".step", ".stp"}:
        return "step"
    if suffix == ".stl":
        return "stl"
    raise ValueError("Unsupported export format. Use a .step, .stp, or .stl destination.")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
