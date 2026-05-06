"""
IRI Standards Agent — Portable Agent Module
Uses Claude Opus via Databricks Foundation Model API.
"""
import os
import sys
import traceback

from strands import Agent
from strands.models.openai import OpenAIModel

from agent.tools import AGENT_TOOLS
from agent.system_prompt import SYSTEM_PROMPT


def create_agent(
    model_id: str = None,
) -> Agent:
    """Create and return the IRI Standards Agent.

    Uses Databricks-hosted Claude via the OpenAI-compatible serving endpoint.
    Automatically resolves workspace host and token from the runtime context.

    Args:
        model_id: Model identifier. Falls back to MODEL_ID env var,
                  then to "databricks-claude-opus-4-7".
    """
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    host = w.config.host.rstrip("/")

    # On serverless runtime, w.config.token is None — extract from auth headers
    auth_headers = w.config.authenticate()
    token = auth_headers.get("Authorization", "").replace("Bearer ", "")

    model_id = model_id or os.environ.get("MODEL_ID", "databricks-claude-opus-4-7")

    model = OpenAIModel(
        client_args={
            "api_key": token,
            "base_url": f"{host}/serving-endpoints",
        },
        model_id=model_id,
        params={"max_tokens": 16384},
    )

    agent = Agent(
        model=model,
        tools=AGENT_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )

    print(f"[agent] IRI Standards Agent initialized", flush=True)
    print(f"[agent]   Model: {model_id}", flush=True)
    print(f"[agent]   Host: {host}", flush=True)
    print(f"[agent]   Tools: {len(AGENT_TOOLS)}", flush=True)

    return agent
