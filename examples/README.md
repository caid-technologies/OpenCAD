# OpenCAD Examples

A collection of runnable example projects that showcase the OpenCAD APIs.
Each example is self-contained with its own README and source files.

## Overview

| # | Name | API surface | Needs running services? |
|---|------|-------------|------------------------|
| 01 | [Hello Part](01_hello_part/) | Headless fluent API (`Part`, `Sketch`) | No |
| 02 | [Parametric Bracket](02_parametric_bracket/) | Headless fluent API — sketch/extrude/pattern | No |
| 03 | [REST API Client](03_rest_api_client/) | Kernel REST API (`/operations`, `/shapes`) | Yes |
| 04 | [Sketch Solver](04_sketch_solver/) | Solver REST API (`/sketch/solve`, `/sketch/diagnose`) | Yes |
| 05 | [Feature Tree](05_feature_tree/) | Tree REST API (CRUD, rebuild, branches) | Yes |
| 06 | [Agent Chat](06_agent_chat/) | Agent REST API (`/chat`) | Yes + OpenAI key |

## Prerequisites

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[full]"      # from the repository root
```

## Running the headless examples (01 & 02)

No backend processes are needed. Run the scripts directly from the
repository root after installing the package:

```bash
python examples/01_hello_part/hello_part.py
python examples/02_parametric_bracket/bracket.py
```

## Running the REST examples (03–06)

Start the backend services in separate terminals:

```bash
python -m uvicorn opencad_kernel.api:app --reload --port 8000
python -m uvicorn opencad_solver.api:app --reload --port 8001
python -m uvicorn opencad_tree.api:app   --reload --port 8002
python -m uvicorn opencad_agent.api:app  --reload --port 8003
```

Then run the example scripts:

```bash
python examples/03_rest_api_client/client.py
python examples/04_sketch_solver/solver_demo.py
python examples/05_feature_tree/tree_demo.py
python examples/06_agent_chat/agent_demo.py   # requires OPENAI_API_KEY
```

Service base URLs can be overridden with environment variables:

```
KERNEL_URL=http://127.0.0.1:8000
SOLVER_URL=http://127.0.0.1:8001
TREE_URL=http://127.0.0.1:8002
AGENT_URL=http://127.0.0.1:8003
```
