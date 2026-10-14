"""Household conversation: one streamed turn per request (text in, text out; voice is the UI's job)."""

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import config
from app.models import Agent, Message, Model, Role
from app.orchestrator import run_household_turn
from app.store import connect, init_schema, messages
from app.store.households import ensure_household

router = APIRouter(prefix="/api/household")

GREETING = (
    "Hi, I'm Anyaa. I'll plan meals with you and keep your cook in the loop. "
    "Let's start with who eats at home?"
)


class TurnRequest(Model):
    text: str


class ResetResult(Model):
    ok: bool


async def _sse(text: str) -> AsyncIterator[str]:
    try:
        async for event in run_household_turn(config.HOUSEHOLD_ID, text):
            yield f"data: {event.model_dump_json()}\n\n"
    except Exception as error:  # surface failures to the UI instead of a dead stream
        yield f"data: {json.dumps({'type': 'error', 'message': str(error)})}\n\n"


@router.post("/turn")
async def turn(body: TurnRequest) -> StreamingResponse:
    return StreamingResponse(_sse(body.text), media_type="text/event-stream")


@router.get("/messages")
def history() -> list[Message]:
    """Conversation so far; a fresh household starts with Anyaa's greeting."""
    conn = connect(config.DB_PATH)
    try:
        found = messages.recent_messages(conn, config.HOUSEHOLD_ID, Agent.HOUSEHOLD, 200)
        if not found:
            found = [messages.append_message(conn, config.HOUSEHOLD_ID, Agent.HOUSEHOLD, Role.ASSISTANT, GREETING)]
        return found
    finally:
        conn.close()


@router.post("/reset")
def reset() -> ResetResult:
    """Start over: wipe the household database (Swiggy login and address are kept)."""
    config.DB_PATH.unlink(missing_ok=True)
    conn = connect(config.DB_PATH)
    init_schema(conn)
    ensure_household(conn, config.HOUSEHOLD_ID)
    conn.close()
    return ResetResult(ok=True)
