# Example 04 — Sketch Solver

Shows how to use the **Constraint Solver REST API** to define 2-D geometric
sketches, apply constraints, solve them, and introspect the constraint graph.

## What this example shows

- Checking which solver backend is active (`/backend`)
- Defining a sketch with points, lines, and circles
- Adding geometric constraints (horizontal, vertical, distance, fixed, equal)
- Solving the sketch (`POST /sketch/solve`)
- Checking constraint consistency without modifying positions (`POST /sketch/check`)
- Full constraint-graph introspection (`POST /sketch/diagnose`):
  - Degrees of freedom (DOF) count
  - Jacobian sparsity
  - Per-constraint residuals
  - Over/under-constrained variable identification

## Sketches demonstrated

1. **Simple rectangle** — 4 lines, horizontal/vertical constraints, fixed corner
2. **Constrained circle** — circle with fixed center and radius
3. **Diagnosed sketch** — deliberately under-constrained to show DOF analysis

## Requirements

```bash
python -m uvicorn opencad_solver.api:app --reload --port 8001
```

## Run

```bash
python examples/04_sketch_solver/solver_demo.py
```
