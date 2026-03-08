# Example 02 — Parametric Bracket

A more complete **headless scripting** example that builds a mechanical
mounting bracket entirely in-process using the `Part` and `Sketch` fluent APIs.

## What this example shows

- Using `Sketch` to draw a 2-D profile (rectangle)
- Extruding the sketch into a 3-D solid
- Adding chamfer/fillet finishing operations
- Using `linear_pattern` to create an evenly spaced bolt-hole array
- Serialising the feature tree to JSON (for reloading or CI inspection)

## Design

```
  ┌─────────────────────────────────────────┐
  │  ○    ○    ○    ○    ○    ○    ○    ○  │  ← 8 bolt holes, linear pattern
  │                                         │
  │                                         │
  └─────────────────────────────────────────┘
        120 mm × 40 mm × 8 mm base plate
```

## Run

```bash
python examples/02_parametric_bracket/bracket.py
```

## Expected output

```
✅ Base plate extruded  feat-0002
✅ First hole cut       feat-0005
✅ Bolt hole pattern    feat-0006
Feature tree: 7 nodes
✅ Tree JSON → /tmp/bracket_tree.json
```
