"""
IRI Standards Agent — Portable Agent Module
Works with any OpenAI-compatible API endpoint.
"""
import os
import sys
import traceback

from strands import Agent
from strands.models.openai import OpenAIModel

from agent.tools import AGENT_TOOLS
from agent.system_prompt import SYSTEM_PROMPT


def create_agent(
    api_key: str = None,
    base_url: str = None,
    model_id: str = None,
) -> Agent:
    """Create and return the IRI Standards Agent.

    Args:
        api_key:  OpenAI-compatible API key. Falls back to OPENAI_API_KEY env var.
        base_url: API base URL. Falls back to OPENAI_BASE_URL env var.
                  Leave unset to use the default OpenAI endpoint.
        model_id: Model identifier. Falls back to MODEL_ID env var,
                  then to "gpt-4o".
    """
    api_key  = api_key  or os.environ.get("OPENAI_API_KEY", "")
    base_url = base_url or os.environ.get("OPENAI_BASE_URL", None)
    model_id = model_id or os.environ.get("MODEL_ID", "gpt-4o")

    if not api_key:
        raise RuntimeError(
            "No API key provided. Set OPENAI_API_KEY in your environment "
            "or pass api_key to create_agent()."
        )

    client_args = {"api_key": api_key}
    if base_url:
        client_args["base_url"] = base_url

    model = OpenAIModel(
        client_args=client_args,
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
    print(f"[agent]   Base URL: {base_url or '(default OpenAI)'}", flush=True)
    print(f"[agent]   Tools: {len(AGENT_TOOLS)}", flush=True)

    return agent
