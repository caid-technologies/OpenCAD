# Example 01 — Hello Part

Demonstrates the **headless fluent API** (`Part` and `Sketch`) that runs
entirely in-process — no HTTP services needed.

## What this example shows

- Creating primitive shapes (`box`, `cylinder`)
- Performing a boolean cut to subtract one shape from another
- Applying edge fillets
- Inspecting the resulting feature tree
- Exporting the part to a STEP file

## Run

```bash
# From the repository root (after pip install -e ".[full]")
python examples/01_hello_part/hello_part.py
```

## Expected output

```
✅ Created box:       feat-0001  shape_id=box-0001
✅ Created cylinder:  feat-0002  shape_id=cyl-0001
✅ Boolean cut:       feat-0003
✅ Fillet:            feat-0004
Feature tree has 5 nodes (including root)
✅ Exported to /tmp/hello_part.step
```
