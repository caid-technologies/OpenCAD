"""
Example 05 — Feature Tree
==========================
Demonstrates the Feature Tree REST API for parametric DAG management.

Demonstrates:
  - Creating a tree and adding feature nodes
  - Editing parameters (triggering stale propagation)
  - Rebuilding the tree
  - Branching for design variants
  - Serialise/deserialise round-trip
  - Suppression / unsuppression

Prerequisites:
  python -m uvicorn opencad_tree.api:app --reload --port 8002
"""

from __future__ import annotations

import json
import os
import urllib.request

TREE_URL = os.environ.get("TREE_URL", "http://127.0.0.1:8002")

# Unique tree ID for this demo run
TREE_ID = "example-tree-05"


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def patch(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())


def section(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


def print_tree(tree: dict) -> None:
    """Print a compact summary of the feature tree."""
    nodes = tree.get("nodes", {})
    print(f"  revision={tree.get('revision', '?')}  "
          f"branch={tree.get('active_branch', '?')}  "
          f"nodes={len(nodes)}")
    for node in nodes.values():
        deps = ", ".join(node.get("depends_on", [])) or "—"
        print(f"  [{node['status']:>10}]  {node['id']:18}  "
              f"op={node['operation']:20}  deps=[{deps}]")


# ── Demo steps ─────────────────────────────────────────────────────────────────

def step1_create_tree() -> dict:
    section("1. Create an empty feature tree")
    tree_payload = {
        "root_id": TREE_ID,
        "nodes": {
            TREE_ID: {
                "id": TREE_ID,
                "name": "Root",
                "operation": "root",
                "parameters": {},
                "depends_on": [],
                "status": "built",
            },
        },
    }
    tree = post(f"{TREE_URL}/trees", tree_payload)
    print(f"  Created tree: {tree['root_id']}")
    print_tree(tree)
    return tree


def step2_add_nodes() -> dict:
    section("2. Add feature nodes: box, cylinder, boolean cut")

    # Node 1: create_box
    box_node = {
        "id": "feat-box",
        "name": "Base Box",
        "operation": "create_box",
        "parameters": {"length": 60, "width": 40, "height": 15},
        "depends_on": [TREE_ID],
        "status": "pending",
    }
    tree = post(f"{TREE_URL}/trees/{TREE_ID}/nodes", box_node)
    print(f"  Added feat-box  → {len(tree['nodes'])} nodes")

    # Node 2: create_cylinder
    cyl_node = {
        "id": "feat-cyl",
        "name": "Hole Cylinder",
        "operation": "create_cylinder",
        "parameters": {"radius": 6, "height": 20},
        "depends_on": [TREE_ID],
        "status": "pending",
    }
    tree = post(f"{TREE_URL}/trees/{TREE_ID}/nodes", cyl_node)
    print(f"  Added feat-cyl  → {len(tree['nodes'])} nodes")

    # Node 3: boolean_cut (depends on both previous nodes)
    cut_node = {
        "id": "feat-cut",
        "name": "Cut Hole",
        "operation": "boolean_cut",
        "parameters": {"shape_a_id": "feat-box", "shape_b_id": "feat-cyl"},
        "depends_on": ["feat-box", "feat-cyl"],
        "status": "pending",
    }
    tree = post(f"{TREE_URL}/trees/{TREE_ID}/nodes", cut_node)
    print(f"  Added feat-cut  → {len(tree['nodes'])} nodes")
    print_tree(tree)
    return tree


def step3_rebuild() -> dict:
    section("3. Rebuild the tree")
    tree = post(f"{TREE_URL}/trees/{TREE_ID}/rebuild", {"continue_on_error": False})
    print_tree(tree)
    return tree


def step4_edit_and_rebuild() -> dict:
    section("4. Edit box dimensions → stale propagation → rebuild")
    # Change the box size; this should mark dependent nodes as stale
    tree = patch(
        f"{TREE_URL}/trees/{TREE_ID}/nodes/feat-box",
        {"parameters": {"length": 80, "width": 50, "height": 20}},
    )
    print("  After edit (before rebuild):")
    print_tree(tree)

    tree = post(f"{TREE_URL}/trees/{TREE_ID}/rebuild", {"continue_on_error": False})
    print("\n  After rebuild:")
    print_tree(tree)
    return tree


def step5_suppression() -> dict:
    section("5. Suppress and re-enable the cylinder node")
    tree = post(
        f"{TREE_URL}/trees/{TREE_ID}/nodes/feat-cyl/suppress",
        {"suppressed": True},
    )
    print("  After suppressing feat-cyl:")
    print_tree(tree)

    tree = post(
        f"{TREE_URL}/trees/{TREE_ID}/nodes/feat-cyl/suppress",
        {"suppressed": False},
    )
    print("\n  After re-enabling feat-cyl:")
    print_tree(tree)
    return tree


def step6_branching() -> dict:
    section("6. Create a design variant branch")
    # Snapshot the current main branch into 'variant-A'
    tree = post(f"{TREE_URL}/trees/{TREE_ID}/branches", {
        "branch_name": "variant-A",
        "from_branch": "main",
    })
    print(f"  Created branch 'variant-A'")

    branches_info = get(f"{TREE_URL}/trees/{TREE_ID}/branches")
    print(f"  Active branch : {branches_info['active_branch']}")
    print(f"  All branches  : {branches_info['branches']}")

    # Switch to the new branch
    tree = post(f"{TREE_URL}/trees/{TREE_ID}/branches/variant-A/switch", {})
    print(f"  Switched to   : {tree['active_branch']}")
    return tree


def step7_serialise() -> None:
    section("7. Serialise / deserialise round-trip")
    result = get(f"{TREE_URL}/trees/{TREE_ID}/serialize")
    payload = result["payload"]
    print(f"  Serialised payload length: {len(payload)} chars")

    # Deserialise into a new tree (the service stores it under its root_id)
    restored = post(f"{TREE_URL}/trees/deserialize", {"payload": payload})
    print(f"  Restored tree root_id: {restored['root_id']}  nodes: {len(restored['nodes'])}")


def main() -> None:
    print("OpenCAD Feature Tree Demo")
    print("=" * 60)

    step1_create_tree()
    step2_add_nodes()
    step3_rebuild()
    step4_edit_and_rebuild()
    step5_suppression()
    step6_branching()
    step7_serialise()

    print("\n✅ Demo complete.")


if __name__ == "__main__":
    main()
