"""Household turn runner: phase-scoped tools, context building, persistence and logging."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from app import clock, config
from app.events import log_event
from app.llm import stream_turn
from app.llm.events import Done, TextDelta, ToolCalled, ToolFinished, TurnEvent
from app.models import Agent, Event, EventType, Message, Phase, Role
from app.services.profile import render_profile
from app.store import connect, households, messages
from app.tools.base import Tool, ToolContext
from app.tools.onboarding import ONBOARDING_TOOLS

PROMPTS = Path(__file__).parent / "agents" / "prompts"
HISTORY_TURNS = 16

PHASE_TOOLS: dict[Phase, list[Tool]] = {
    Phase.ONBOARDING: ONBOARDING_TOOLS,
}
PHASE_PROMPTS: dict[Phase, str] = {
    Phase.ONBOARDING: "household_onboarding.md",
}


def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def build_system(phase: Phase, profile: str, now_text: str) -> str:
    phase_prompt = _prompt(PHASE_PROMPTS[phase]) if phase in PHASE_PROMPTS else ""
    return "\n\n".join(
        [
            _prompt("household_persona.md"),
            phase_prompt,
            f"# Current household profile\n\n{profile}",
            f"# Now\n\n{now_text}. Phase: {phase.value}.",
        ]
    )


def build_prompt(history: list[Message], user_text: str) -> str:
    """Prior turns as a transcript, then the new message. Keeps the backend stateless."""
    lines = [f"{'User' if m.role is Role.USER else 'Anyaa'}: {m.content}" for m in history]
    transcript = "\n".join(lines) if lines else "(this is the first message)"
    return f"Conversation so far:\n{transcript}\n\nUser's new message:\n{user_text}"


def _log(household_id: int, turn_id: str, phase: Phase, kind: EventType, data: dict, latency_ms: int | None = None) -> None:
    log_event(
        Event(
            ts=clock.real_now(),
            household_id=household_id,
            turn_id=turn_id,
            agent=Agent.HOUSEHOLD,
            phase=phase,
            type=kind,
            data=data,
            latency_ms=latency_ms,
        )
    )


async def run_household_turn(household_id: int, user_text: str) -> AsyncIterator[TurnEvent]:
    conn = connect(config.DB_PATH)
    turn_id = uuid.uuid4().hex
    try:
        household = households.ensure_household(conn, household_id)
        phase = household.phase
        history = messages.recent_messages(conn, household_id, Agent.HOUSEHOLD, HISTORY_TURNS)
        messages.append_message(conn, household_id, Agent.HOUSEHOLD, Role.USER, user_text)

        now = clock.now(conn, household_id)
        system = build_system(phase, render_profile(conn, household_id), now.strftime("%A %d %B %Y, %H:%M"))
        tools = PHASE_TOOLS.get(phase, [])
        ctx = ToolContext(conn=conn, household_id=household_id)

        reply: list[str] = []
        async for event in stream_turn(system, build_prompt(history, user_text), tools, ctx):
            if isinstance(event, TextDelta):
                reply.append(event.text)
            elif isinstance(event, ToolCalled):
                _log(household_id, turn_id, phase, EventType.TOOL_CALL, {"name": event.name, "args": event.args})
            elif isinstance(event, ToolFinished):
                _log(household_id, turn_id, phase, EventType.TOOL_RESULT, {"name": event.name, "result": event.result}, event.latency_ms)
            elif isinstance(event, Done):
                _log(household_id, turn_id, phase, EventType.LLM_CALL, {"stop": event.stop, "turns": event.turns, "usage": event.usage}, event.duration_ms)
            yield event

        text = "".join(reply).strip()
        if text:
            messages.append_message(conn, household_id, Agent.HOUSEHOLD, Role.ASSISTANT, text)
        new_phase = households.ensure_household(conn, household_id).phase
        if new_phase is not phase:
            _log(household_id, turn_id, new_phase, EventType.PHASE_CHANGE, {"from": phase.value, "to": new_phase.value})
    except Exception as error:
        _log(household_id, turn_id, Phase.ONBOARDING, EventType.ERROR, {"error": repr(error)})
        raise
    finally:
        conn.close()
