# Example 05 — Feature Tree

Shows how to use the **Feature Tree REST API** to build, inspect, modify,
and rebuild a parametric feature DAG without running any client-side Python
geometry code.

## What this example shows

- Creating a feature tree from scratch
- Adding feature nodes (box, cylinder, boolean cut)
- Editing a node's parameters and watching dependents go stale
- Triggering a tree rebuild (`POST /trees/{id}/rebuild`)
- Creating a branch for variant exploration
- Serialising / deserialising a tree snapshot
- Suppressing and re-enabling a feature

## Requirements

```bash
python -m uvicorn opencad_tree.api:app --reload --port 8002
```

## Run

```bash
python examples/05_feature_tree/tree_demo.py
```
