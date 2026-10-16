"""Runs one turn of an agent node (household or cook) on the Claude Agent SDK.

The SDK keeps each node's conversation in a session (resumed every turn), runs the tool loop, and
calls our hook after every tool. We pick the node, attach live context, clean the reply, save it.
"""

import dataclasses
import re
from collections.abc import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
)

from app import clock, config, obs, queries, voice
from app.db import db
from app.flow import COOK_NODE, Node, household_node
from app.models import Agent, Role

RECENT = 6  # messages shown to a node when it starts, so it can pick up the thread
STAGE_DIRECTION = re.compile(r"^\s*[*_(\[].*[)\]*_]\s*$", re.DOTALL)  # "(waiting for their answer)", "*pauses*"
LEAKS = [  # things a model sometimes echoes from its prompt; never spoken
    re.compile(r"<context>.*?(</context>|$)", re.DOTALL),
    re.compile(r"<thinking>.*?(</thinking>|$)", re.DOTALL),
    re.compile(r"<system-reminder>.*?(</system-reminder>|</thinking>|$)", re.DOTALL),
    re.compile(r"</?(thinking|context|system-reminder)>"),
    re.compile(r"RECENT CONVERSATION.*?(?:\n\s*\n|$)", re.DOTALL),
    re.compile(r"^\s*\[start\].*$", re.MULTILINE),
]


def _clean(text: str) -> str:
    for leak in LEAKS:
        text = leak.sub("", text)
    return text.strip()


def _speakable(text: str) -> bool:
    return bool(text.strip()) and not STAGE_DIRECTION.match(text)


def agent_options(node: Node, session_id: str | None, turn: obs.Turn) -> ClaudeAgentOptions:
    async def log_tool_call(hook_input, _tool_use_id, _context) -> dict:
        turn.log("tool_call", tool=hook_input["tool_name"].removeprefix("mcp__anyaa__"),
                 args=hook_input["tool_input"], result=hook_input.get("tool_response"))
        return {}

    return ClaudeAgentOptions(
        model=config.LLM_MODEL,
        system_prompt=node.system_prompt(),
        mcp_servers={"anyaa": create_sdk_mcp_server(name="anyaa", tools=node.tools)},
        allowed_tools=[f"mcp__anyaa__{t.name}" for t in node.tools],
        hooks={"PostToolUse": [HookMatcher(hooks=[log_tool_call])]},
        resume=session_id,              # continue this node's conversation
        tools=[],                       # no built-in tools (Bash, Read, Write, ...)
        setting_sources=[],             # ignore ~/.claude settings
        thinking={"type": "disabled"},  # faster replies
        max_turns=12,
        env={"MCP_TOOL_TIMEOUT": "300000"},  # planning tools can take a minute or two
        cwd=str(config.DATA_DIR),
    )


def _prompt(conn, node: Node, text: str, session_id: str | None) -> str:
    """Live context rides on the message (the system prompt stays fixed for the session)."""
    context = f"Now: {clock.now(conn):%A %d %B, %H:%M}\n{node.context(conn)}"
    if session_id is None:  # a node's first turn: show how the conversation got here
        if recent := queries.list_messages(conn, node.agent)[-RECENT:]:
            them = "User" if node.agent == Agent.HOUSEHOLD else "Cook"
            context += "\n\nRECENT CONVERSATION\n" + "\n".join(
                f"{them if m.role == Role.USER else 'You'}: {m.content}" for m in recent)
    context += f"\n\nYOU ARE IN: {node.name}. {node.scope}"
    if node.hint and (nudge := node.hint(text)):
        context += f"\n{nudge}"
    return f"<context>\n{context}\n</context>\n\n{text}"


async def _run(node: Node, text: str) -> AsyncIterator[dict]:
    """One SDK turn. Yields tool events, then {"type": "result", "text", "session_id"}."""
    with db() as conn:
        session_id = queries.get_session(conn, node.agent, node.name)
        prompt = _prompt(conn, node, text, session_id)

    turn = obs.start_turn(node.agent, node=node.name, text=text)
    reply, said = "", []  # said: every real thing it wrote; the reply is the last one
    try:
        async with ClaudeSDKClient(agent_options(node, session_id, turn)) as agent:
            await agent.query(prompt)
            async for message in agent.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and _speakable(_clean(block.text)):
                            said.append(_clean(block.text))
                        if isinstance(block, ToolUseBlock):
                            yield {"type": "tool", "name": block.name.removeprefix("mcp__anyaa__"), "args": block.input}
                elif isinstance(message, ResultMessage):
                    session_id = message.session_id
                    # The final text is usually the reply. If it's empty or a stage direction, the model
                    # already said the real thing before its last tool call: use that instead.
                    final = _clean(message.result or "")
                    reply = final if _speakable(final) else (said[-1] if said else "")
                    if message.is_error or "session limit" in reply.lower():
                        turn.log("error", error=reply or message.subtype)
                        reply = voice.say("limit" if "limit" in reply.lower() else "error")
    except Exception as error:
        turn.log("error", error=repr(error))
        reply = voice.say("error")

    turn.log("turn_end", reply=reply)
    yield {"type": "result", "text": reply, "session_id": session_id}


async def run_household_turn(text: str, *, opener: bool = False) -> AsyncIterator[dict]:
    """Yields {"type": "tool"} as the agent works, then {"type": "reply"} with its answer.

    When a turn finishes a node, that node stays quiet and the next node opens right away.
    """
    with db() as conn:
        if not opener:
            queries.add_message(conn, Agent.HOUSEHOLD, Role.USER, text)
        node = household_node(conn)
    if node is None:
        return

    result = {}
    async for event in _run(node, text):
        if event["type"] == "result":
            result = event
        else:
            yield event

    with db() as conn:
        if result.get("session_id"):
            queries.save_session(conn, Agent.HOUSEHOLD, node.name, result["session_id"])
        next_node = household_node(conn)
        moved_on = next_node is not None and next_node.name != node.name
        if result.get("text") and not moved_on:
            queries.add_message(conn, Agent.HOUSEHOLD, Role.ASSISTANT, result["text"])
            yield {"type": "reply", "text": result["text"]}

    if moved_on:
        async for event in run_household_turn(next_node.opener, opener=True):
            yield event


async def run_cook_turn(text: str) -> str:
    """The cook said something (Telegram). Returns what Anyaa replies to them."""
    with db() as conn:
        queries.add_message(conn, Agent.COOK, Role.USER, text)
        node = dataclasses.replace(COOK_NODE, name=f"COOK_CHAT {clock.now(conn):%Y-%m-%d}")  # a fresh chat each day
    result = {}
    async for event in _run(node, text):
        if event["type"] == "result":
            result = event
    with db() as conn:
        if result.get("session_id"):
            queries.save_session(conn, Agent.COOK, node.name, result["session_id"])
        if result.get("text"):
            queries.add_message(conn, Agent.COOK, Role.ASSISTANT, result["text"])
    return result.get("text", "")
