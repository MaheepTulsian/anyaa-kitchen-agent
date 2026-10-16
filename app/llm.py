"""One-shot structured LLM calls (planner, safety check) on the Claude Agent SDK.

    plan = await llm.ask(MealPlan, system="You plan meals...", prompt="...")

The SDK returns JSON matching the Pydantic model's schema; we validate it with the same model, so a
bad answer raises instead of being used.
"""

from typing import TypeVar

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import BaseModel

from app import config

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


async def ask(schema: type[T], *, system: str, prompt: str, model: str | None = None) -> T:
    options = ClaudeAgentOptions(
        model=model or config.LLM_MODEL,
        system_prompt=system,
        output_format={"type": "json_schema", "schema": schema.model_json_schema()},
        tools=[],
        setting_sources=[],
        thinking={"type": "disabled"},  # the prompts carry the reasoning; this is ~3x faster
        max_turns=3,
        cwd=str(config.DATA_DIR),
    )
    result = None
    async for message in query(prompt=prompt, options=options):  # let the stream finish cleanly
        if isinstance(message, ResultMessage):
            result = message
    if result is None or result.structured_output is None:
        raise LLMError(f"no structured output: {result.result if result else 'no reply'}")
    return schema.model_validate(result.structured_output)
