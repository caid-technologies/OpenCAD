# Example 06 — Agent Chat

Demonstrates the **AI Agent REST API** which accepts a natural-language
description and plans + executes a sequence of CAD operations autonomously.

## What this example shows

- Sending a natural-language design prompt to the agent
- Receiving a structured response that includes:
  - Human-readable explanation
  - A list of operations that were executed (tool, status, arguments)
  - The updated `FeatureTree` after execution
- Multi-turn conversation (follow-up refinement)
- Using the `reasoning=true` flag for extended chain-of-thought output

## Requirements

1. The agent service must be running:
   ```bash
   python -m uvicorn opencad_agent.api:app --reload --port 8003
   ```
2. An `OPENAI_API_KEY` environment variable must be set:
   ```bash
   export OPENAI_API_KEY=sk-...
   ```

## Run

```bash
OPENAI_API_KEY=sk-... python examples/06_agent_chat/agent_demo.py
```

## Note on API key

The agent service uses the `openai` Python library to call an LLM.
If no API key is set, the agent service will start but chat requests will
return an error — that is expected and safe.
