# opencad

The OpenCAD core: geometry kernel, constraint solver, feature tree, and the
fluent modelling API — with no web framework and no network dependency.

Install:

```bash
pip install opencad          # pydantic + numpy only
pip install "opencad[occt]"  # add the OCCT B-rep backend
pip install "opencad[full]"  # OCCT + scipy solver + networkx graph analysis
```

Use:

```python
from opencad import Part, Sketch

profile = Sketch(name="Plate").rect(80, 30).circle(3, center=(8, 8), subtract=True)
plate = Part().extrude(profile, depth=4, name="Plate")
plate.fillet(edges="all", radius=1.0)
```

Every fluent call appends a node to a rebuildable feature DAG, which you can
serialize, edit, and replay. See the repository `ARCHITECTURE.md` for the
kernel/solver/tree design and `TOPOLOGY.md` for topological naming.

## Packages

| Module | Responsibility |
|--------|----------------|
| `opencad` | Fluent `Part`/`Sketch` API, `RuntimeContext`, CLI, design artifacts |
| `opencad.kernel` | B-rep operations, OCCT and analytic backends, `KernelClient` |
| `opencad.solver` | 2-D constraint solving (NumPy/SciPy and SolveSpace backends) |
| `opencad.tree` | Feature DAG, incremental rebuild, branching, expressions |

## Related distributions

- `opencad-agent` — natural-language modelling on top of this package
- `opencad-backend` — FastAPI HTTP service exposing all of the above

## Tests

```bash
pytest
```

The suite runs against this package alone. A few integration tests exercise
repository files (`examples/`, `docs/schemas/`) and skip automatically when
the package is tested outside a monorepo checkout.
