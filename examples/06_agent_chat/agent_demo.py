"""
Example 06 — Agent Chat
========================
Demonstrates the OpenCAD AI Agent REST API.

Sends natural-language design prompts to the agent, which plans and
executes a sequence of CAD operations and returns both a human-readable
explanation and a structured operation log.

Prerequisites:
  1. python -m uvicorn opencad_agent.api:app --reload --port 8003
  2. OPENAI_API_KEY environment variable set

If OPENAI_API_KEY is not set the demo will still run; the agent service
will respond with an error message from the LLM layer.
"""

from __future__ import annotations

import json
import os
import textwrap
import urllib.request

AGENT_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8003")


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read())


def section(title: str) -> None:
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


# ── An empty seed tree required by the agent API ─────────────────────────────

EMPTY_TREE = {
    "root_id": "root",
    "nodes": {
        "root": {
            "id": "root",
            "name": "Root",
            "operation": "seed",
            "parameters": {},
            "depends_on": [],
            "status": "built",
        },
    },
    "active_branch": "main",
}


# ── Print helpers ─────────────────────────────────────────────────────────────

def print_response(resp: dict) -> None:
    """Print a chat response in a readable format."""
    print("\n  [Agent response]")
    text = resp.get("response", "")
    for line in textwrap.wrap(text, width=70, initial_indent="    ", subsequent_indent="    "):
        print(line)

    ops = resp.get("operations_executed", [])
    if ops:
        print(f"\n  Operations executed ({len(ops)}):")
        for op in ops:
            status = "✅" if op.get("status") == "ok" else "❌"
            print(f"  {status}  {op['tool']:20}  args={json.dumps(op.get('arguments', {}))[:60]}")

    new_tree = resp.get("new_tree_state", {})
    node_count = len(new_tree.get("nodes", {}))
    print(f"\n  Updated feature tree: {node_count} nodes")


# ── Demo steps ────────────────────────────────────────────────────────────────

def step1_health_check() -> None:
    section("1. Health check")
    import urllib.error
    try:
        with urllib.request.urlopen(f"{AGENT_URL}/healthz", timeout=5) as resp:  # noqa: S310
            result = json.loads(resp.read())
        print(f"  ✅ Agent service: {result}")
    except urllib.error.URLError as exc:
        print(f"  ❌ Agent service not reachable: {exc}")
        print("     Start it with: python -m uvicorn opencad_agent.api:app --reload --port 8003")
        raise SystemExit(1) from exc


def step2_simple_prompt(tree: dict) -> dict:
    section("2. Simple design prompt")
    request_body = {
        "message": "Create a mounting bracket: a flat rectangular base plate with four bolt holes.",
        "tree_state": tree,
        "conversation_history": [],
        "reasoning": False,
    }
    print(f"  Prompt: {request_body['message']!r}")
    resp = post(f"{AGENT_URL}/chat", request_body)
    print_response(resp)
    return resp.get("new_tree_state", tree)


def step3_follow_up(tree: dict, history: list) -> dict:
    section("3. Follow-up: refine the design")
    request_body = {
        "message": "Now add fillets to the top edges of the base plate.",
        "tree_state": tree,
        "conversation_history": history,
        "reasoning": False,
    }
    print(f"  Prompt: {request_body['message']!r}")
    resp = post(f"{AGENT_URL}/chat", request_body)
    print_response(resp)
    return resp.get("new_tree_state", tree)


def step4_reasoning_mode(tree: dict) -> None:
    section("4. Reasoning mode (extended chain-of-thought)")
    request_body = {
        "message": "Explain the feature tree structure you've built so far.",
        "tree_state": tree,
        "conversation_history": [],
        "reasoning": True,
    }
    print(f"  Prompt: {request_body['message']!r}  reasoning=True")
    resp = post(f"{AGENT_URL}/chat", request_body)
    print_response(resp)


def main() -> None:
    print("OpenCAD Agent Chat Demo")
    print("=" * 60)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("⚠️  OPENAI_API_KEY is not set — agent LLM calls will fail.")
        print("   Set it with: export OPENAI_API_KEY=sk-...")

    step1_health_check()

    tree = EMPTY_TREE
    history: list[dict] = []

    updated_tree = step2_simple_prompt(tree)
    history.append({"role": "user",      "content": "Create a mounting bracket..."})
    history.append({"role": "assistant", "content": "(see step 2 response)"})

    updated_tree = step3_follow_up(updated_tree, history)

    step4_reasoning_mode(updated_tree)

    print("\n✅ Demo complete.")


if __name__ == "__main__":
    main()
