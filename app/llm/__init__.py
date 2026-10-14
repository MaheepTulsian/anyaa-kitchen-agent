"""LLM backends behind one function: `stream_turn(system, prompt, tools, ctx)`.

LLM_BACKEND=agent_sdk (default, local Claude login) | api (Anthropic API key; not wired yet).
"""

from app import config

if config.LLM_BACKEND == "agent_sdk":
    from app.llm.agent_sdk import stream_turn
else:
    raise RuntimeError(f"LLM_BACKEND={config.LLM_BACKEND!r} is not implemented yet")

__all__ = ["stream_turn"]
