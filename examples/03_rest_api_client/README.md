# Example 03 — REST API Client

Demonstrates how to talk to the **OpenCAD Kernel REST API** directly from Python
using the standard `urllib` library (no third-party dependencies beyond the
installed package).

## What this example shows

- Health-checking all four backend services
- Listing available operations
- Creating shapes via `POST /operations/{name}`
- Fetching the mesh for a shape
- Retrieving topology (face/edge references)
- Running an operation replay

## Requirements

All four backend services must be running. Start them with:

```bash
python -m uvicorn opencad_kernel.api:app --reload --port 8000
python -m uvicorn opencad_solver.api:app --reload --port 8001
python -m uvicorn opencad_tree.api:app   --reload --port 8002
python -m uvicorn opencad_agent.api:app  --reload --port 8003
```

## Run

```bash
python examples/03_rest_api_client/client.py
```

## Configuration

Override the default service URLs with environment variables:

| Variable | Default |
|----------|---------|
| `KERNEL_URL` | `http://127.0.0.1:8000` |
| `SOLVER_URL` | `http://127.0.0.1:8001` |
| `TREE_URL`   | `http://127.0.0.1:8002` |
| `AGENT_URL`  | `http://127.0.0.1:8003` |
