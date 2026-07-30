from __future__ import annotations

import argparse
import runpy
from pathlib import Path

from opencad.runtime import RuntimeContext, get_default_context, set_default_context


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
    build_parser.set_defaults(func=_cmd_build)

    run_parser = subparsers.add_parser("run", help="Run a Python script with the opencad fluent API")
    run_parser.add_argument("script", help="Python script path")
    run_parser.add_argument("--export", help="Optional STEP output path")
    run_parser.add_argument("--tree-output", help="Optional path to write resulting feature tree JSON")
    run_parser.add_argument(
        "--id-strategy",
        default="readable",
        choices=["readable", "uuid"],
        help="Shape ID strategy for script execution",
    )
    run_parser.set_defaults(func=_cmd_run)

    return parser


def _cmd_build(args: argparse.Namespace) -> int:
    context = RuntimeContext(id_strategy=args.id_strategy)
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
    context = RuntimeContext(id_strategy=args.id_strategy)
    set_default_context(context)

    script_path = Path(args.script)
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    runpy.run_path(str(script_path), run_name="__main__")

    current = get_default_context()
    if args.export:
        if not current.last_shape_id:
            raise RuntimeError("No shape was produced by the script, cannot export STEP.")
        current.export_step(current.last_shape_id, args.export)
        print(f"Exported STEP to {args.export}")

    if args.tree_output:
        current.save_tree_json(args.tree_output)
        print(f"Wrote tree JSON to {args.tree_output}")

    print(f"Script completed. Nodes: {len(current.tree.nodes)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
