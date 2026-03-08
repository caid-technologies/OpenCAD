"""
Example 04 — Sketch Solver
===========================
Explores the OpenCAD Constraint Solver REST API.

Demonstrates:
  - Querying the active solver backend
  - Defining 2-D sketches (points, lines, circles)
  - Applying constraints (horizontal, vertical, fixed, distance, equal)
  - Solving, checking, and diagnosing sketches

Prerequisites:
  python -m uvicorn opencad_solver.api:app --reload --port 8001
"""

from __future__ import annotations

import json
import os
import urllib.request

SOLVER_URL = os.environ.get("SOLVER_URL", "http://127.0.0.1:8001")


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def section(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


# ── Sketch definitions ────────────────────────────────────────────────────────

# Sketch 1: A rectangle with horizontal/vertical constraints.
# Corner at (0, 0) is fixed; the solver fills in the remaining positions.
RECTANGLE_SKETCH = {
    "entities": {
        "p0": {"id": "p0", "type": "point", "x":  0.0, "y":  0.0},
        "p1": {"id": "p1", "type": "point", "x": 10.0, "y":  0.0},
        "p2": {"id": "p2", "type": "point", "x": 10.0, "y":  6.0},
        "p3": {"id": "p3", "type": "point", "x":  0.0, "y":  6.0},
        "l0": {"id": "l0", "type": "line",  "x1":  0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0},
        "l1": {"id": "l1", "type": "line",  "x1": 10.0, "y1": 0.0, "x2": 10.0, "y2": 6.0},
        "l2": {"id": "l2", "type": "line",  "x1": 10.0, "y1": 6.0, "x2":  0.0, "y2": 6.0},
        "l3": {"id": "l3", "type": "line",  "x1":  0.0, "y1": 6.0, "x2":  0.0, "y2": 0.0},
    },
    "constraints": [
        # Fix the origin corner
        {"id": "c0", "type": "fixed", "a": "p0"},
        # Horizontal and vertical sides
        {"id": "c1", "type": "horizontal",   "a": "l0"},
        {"id": "c2", "type": "vertical",     "a": "l1"},
        {"id": "c3", "type": "horizontal",   "a": "l2"},
        {"id": "c4", "type": "vertical",     "a": "l3"},
        # Width = 10, height = 6
        {"id": "c5", "type": "distance", "a": "p0", "b": "p1", "value": 10.0},
        {"id": "c6", "type": "distance", "a": "p1", "b": "p2", "value":  6.0},
    ],
}

# Sketch 2: A fully constrained circle.
CIRCLE_SKETCH = {
    "entities": {
        "c0": {"id": "c0", "type": "circle", "cx": 0.0, "cy": 0.0, "radius": 5.0},
    },
    "constraints": [
        {"id": "fix_center", "type": "fixed", "a": "c0"},
    ],
}

# Sketch 3: An under-constrained line pair (for DOF demonstration).
UNDERCONSTRAINED_SKETCH = {
    "entities": {
        "l0": {"id": "l0", "type": "line", "x1": 0.0, "y1": 0.0, "x2": 5.0, "y2": 0.0},
        "l1": {"id": "l1", "type": "line", "x1": 5.0, "y1": 0.0, "x2": 5.0, "y2": 4.0},
    },
    "constraints": [
        # Only one constraint — leaves many DOF free
        {"id": "c0", "type": "horizontal", "a": "l0"},
    ],
}


# ── Demo ──────────────────────────────────────────────────────────────────────

def show_backend() -> None:
    section("1. Active solver backend")
    info = get(f"{SOLVER_URL}/backend")
    print(f"  name           : {info['name']}")
    print(f"  supports_3d    : {info.get('supports_3d', False)}")
    print(f"  solvespace_available : {info.get('solvespace_available', False)}")


def solve_rectangle() -> None:
    section("2. Solve rectangle sketch")
    result = post(f"{SOLVER_URL}/sketch/solve", RECTANGLE_SKETCH)
    status = result["status"]
    print(f"  status         : {status}")
    print(f"  iterations     : {result.get('iterations', '?')}")
    print(f"  max_residual   : {result.get('max_residual', '?'):.2e}")

    if status == "SOLVED":
        # Show the solved positions of the corner points
        solved_entities = result["sketch"]["entities"]
        for pid in ("p0", "p1", "p2", "p3"):
            pt = solved_entities.get(pid, {})
            print(f"  {pid}: ({pt.get('x', '?'):.3f}, {pt.get('y', '?'):.3f})")


def check_circle() -> None:
    section("3. Check circle sketch (no solve)")
    result = post(f"{SOLVER_URL}/sketch/check", CIRCLE_SKETCH)
    print(f"  status         : {result['status']}")
    print(f"  max_residual   : {result.get('max_residual', 0):.2e}")
    if result.get("message"):
        print(f"  message        : {result['message']}")


def diagnose_underconstrained() -> None:
    section("4. Diagnose under-constrained sketch")
    result = post(f"{SOLVER_URL}/sketch/diagnose", UNDERCONSTRAINED_SKETCH)
    print(f"  status  : {result['status']}")
    print(f"  DOF     : {result['dof']}")

    jacobian = result.get("jacobian", {})
    print(f"  Jacobian: {jacobian.get('rows')} rows × {jacobian.get('cols')} cols  "
          f"rank={jacobian.get('rank')}")

    under_vars = result.get("under_constrained_variables", [])
    print(f"  Under-constrained variable indices: {under_vars}")

    variables = result.get("variables", [])
    for var in variables:
        free = "FREE" if var["index"] in under_vars else "    "
        print(f"  [{free}] var[{var['index']}] → entity={var['entity_id']}  param={var['parameter_name']}")


def main() -> None:
    print("OpenCAD Sketch Solver Demo")
    print("=" * 60)

    show_backend()
    solve_rectangle()
    check_circle()
    diagnose_underconstrained()

    print("\n✅ Demo complete.")


if __name__ == "__main__":
    main()
