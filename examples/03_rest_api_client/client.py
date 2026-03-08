"""
Example 03 — REST API Client
=============================
Shows how to interact with the OpenCAD backend services over HTTP.

Demonstrates:
  - Health-checking all four services
  - Listing registered kernel operations
  - Creating shapes (box, cylinder, sphere)
  - Fetching mesh data from the kernel
  - Reading topology (face/edge) references
  - Running a kernel operation replay

Prerequisites:
  All four backend services must be running (see README).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

# ── Service base URLs (override via environment variables) ───────────────────
KERNEL_URL = os.environ.get("KERNEL_URL", "http://127.0.0.1:8000")
SOLVER_URL = os.environ.get("SOLVER_URL", "http://127.0.0.1:8001")
TREE_URL   = os.environ.get("TREE_URL",   "http://127.0.0.1:8002")
AGENT_URL  = os.environ.get("AGENT_URL",  "http://127.0.0.1:8003")


# ── Tiny HTTP helpers ─────────────────────────────────────────────────────────

def get(url: str) -> dict:
    """HTTP GET → parsed JSON."""
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def post(url: str, body: dict) -> dict:
    """HTTP POST with JSON body → parsed JSON."""
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
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


# ── Demo steps ────────────────────────────────────────────────────────────────

def check_health() -> None:
    section("1. Health checks")
    services = {
        "Kernel": KERNEL_URL,
        "Solver": SOLVER_URL,
        "Tree":   TREE_URL,
        "Agent":  AGENT_URL,
    }
    for name, base in services.items():
        try:
            result = get(f"{base}/healthz")
            print(f"  ✅ {name:6}  {result}")
        except urllib.error.URLError as exc:
            print(f"  ❌ {name:6}  {exc} — is the service running?")


def list_operations() -> None:
    section("2. Available kernel operations")
    ops: list[str] = get(f"{KERNEL_URL}/operations")
    for op in sorted(ops):
        print(f"  • {op}")
    print(f"\n  Total: {len(ops)} operations")


def create_shapes() -> tuple[str, str, str]:
    section("3. Create shapes")

    box_result = post(f"{KERNEL_URL}/operations/create_box", {
        "payload": {"length": 50, "width": 30, "height": 20},
    })
    box_id = box_result["shape_id"]
    print(f"  ✅ Box       shape_id={box_id}  volume={box_result.get('shape', {}).get('volume', '?'):.1f}")

    cyl_result = post(f"{KERNEL_URL}/operations/create_cylinder", {
        "payload": {"radius": 8, "height": 30},
    })
    cyl_id = cyl_result["shape_id"]
    print(f"  ✅ Cylinder  shape_id={cyl_id}  volume={cyl_result.get('shape', {}).get('volume', '?'):.1f}")

    sph_result = post(f"{KERNEL_URL}/operations/create_sphere", {
        "payload": {"radius": 12},
    })
    sph_id = sph_result["shape_id"]
    print(f"  ✅ Sphere    shape_id={sph_id}  volume={sph_result.get('shape', {}).get('volume', '?'):.1f}")

    return box_id, cyl_id, sph_id


def fetch_mesh(shape_id: str) -> None:
    section("4. Fetch mesh data")
    mesh = get(f"{KERNEL_URL}/shapes/{shape_id}/mesh?deflection=0.5")
    vertices = mesh.get("vertices", [])
    faces = mesh.get("faces", [])
    print(f"  shape_id : {shape_id}")
    print(f"  vertices : {len(vertices)} entries")
    print(f"  faces    : {len(faces)} triangles")
    if vertices:
        print(f"  first vertex : {vertices[0]}")


def fetch_topology(shape_id: str) -> None:
    section("5. Topology (faces and edges)")
    topo = get(f"{KERNEL_URL}/shapes/{shape_id}/topology")
    faces = topo.get("faces", [])
    edges = topo.get("edges", [])
    print(f"  shape_id : {shape_id}")
    print(f"  faces    : {len(faces)}")
    print(f"  edges    : {len(edges)}")
    if faces:
        print(f"  first face id : {faces[0]['id']}")
    if edges:
        print(f"  first edge id : {edges[0]['id']}")


def run_replay() -> None:
    section("6. Operation replay")
    result = post(f"{KERNEL_URL}/operations/replay", {
        "entries": [
            {"operation": "create_box",      "params": {"length": 10, "width": 10, "height": 10}},
            {"operation": "create_cylinder", "params": {"radius": 3, "height": 15}},
            {"operation": "create_sphere",   "params": {"radius": 5}},
        ],
    })
    print(f"  Replayed : {result.get('replayed')} operations")
    for r in result.get("results", []):
        ok = "✅" if r.get("ok") else "❌"
        print(f"  {ok}  {r.get('operation', '?'):20}  shape_id={r.get('shape_id', '—')}")


def get_operation_schema(operation: str) -> None:
    section(f"7. Schema for '{operation}'")
    schema = get(f"{KERNEL_URL}/operations/{operation}/schema")
    print(f"  title   : {schema.get('title', '?')}")
    version = schema.get("x-opencad-version", "?")
    print(f"  version : {version}")
    props = schema.get("properties", {})
    print(f"  fields  : {', '.join(props.keys())}")


def main() -> None:
    print("OpenCAD REST API Client Demo")
    print("=" * 60)

    check_health()
    list_operations()
    box_id, cyl_id, sph_id = create_shapes()
    fetch_mesh(box_id)
    fetch_topology(box_id)
    run_replay()
    get_operation_schema("create_box")

    print("\n✅ Demo complete.")


if __name__ == "__main__":
    main()
