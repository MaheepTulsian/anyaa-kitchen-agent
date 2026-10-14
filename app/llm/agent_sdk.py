"""LLM backend on the Claude Agent SDK (development; uses the local Claude login).

Only our own tools are exposed: built-in tools are disabled and no filesystem settings are
loaded, so the model cannot read or write files on this machine.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    StreamEvent,
    ToolUseBlock,
    create_sdk_mcp_server,
    tool,
)

from app import config
from app.llm.events import Done, TextDelta, ToolCalled, ToolFinished, TurnEvent
from app.tools.base import Tool, ToolContext, run_tool

SERVER = "anyaa"


def _sdk_tool(spec: Tool, ctx: ToolContext, finished: list[ToolFinished]) -> Any:
    @tool(spec.name, spec.description, spec.json_schema())
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        result = await run_tool(spec, ctx, args)
        finished.append(
            ToolFinished(
                name=spec.name,
                args=args,
                result=result,
                latency_ms=int((time.monotonic() - started) * 1000),
            )
        )
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "is_error": not result["ok"],
        }

    return handler


async def stream_turn(
    system: str, prompt: str, tools: list[Tool], ctx: ToolContext, max_turns: int = 8
) -> AsyncIterator[TurnEvent]:
    finished: list[ToolFinished] = []
    server = create_sdk_mcp_server(
        name=SERVER, version="1.0.0", tools=[_sdk_tool(t, ctx, finished) for t in tools]
    )
    options = ClaudeAgentOptions(
        system_prompt=system,
        model=config.LLM_MODEL,
        tools=[],  # no built-in tools (Bash, Read, Write, ...)
        mcp_servers={SERVER: server},
        allowed_tools=[f"mcp__{SERVER}__{t.name}" for t in tools],
        setting_sources=[],  # ignore ~/.claude and project settings
        max_turns=max_turns,
        thinking={"type": "disabled"},  # conversational turns; latency matters more than reasoning
        include_partial_messages=True,
        cwd=str(config.DATA_DIR),
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)
        # Text right before a tool call is narration ("let me save that"): hold each text block
        # until we see what follows it, and drop it if a tool call comes next.
        held: list[str] = []
        spoke = False
        async for message in client.receive_response():
            while finished:
                yield finished.pop(0)
            if isinstance(message, StreamEvent):
                event = message.event
                kind = event.get("type")
                if kind == "content_block_start":
                    block_type = event.get("content_block", {}).get("type")
                    if block_type == "tool_use":
                        held.clear()
                    elif block_type == "text" and held:
                        yield TextDelta(text=("\n" if spoke else "") + "".join(held))
                        spoke, held = True, []
                elif kind == "content_block_delta" and event.get("delta", {}).get("type") == "text_delta":
                    held.append(event["delta"]["text"])
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        yield ToolCalled(name=block.name.removeprefix(f"mcp__{SERVER}__"), args=block.input)
            elif isinstance(message, ResultMessage):
                while finished:
                    yield finished.pop(0)
                if held:  # the final reply
                    yield TextDelta(text=("\n" if spoke else "") + "".join(held))
                yield Done(
                    stop=message.subtype,
                    turns=message.num_turns,
                    duration_ms=message.duration_ms,
                    usage=message.usage or {},
                )
