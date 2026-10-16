"""The cook's side of the day, on Telegram.

    HOUSEHOLD_CHECK  before each visit (2 hours before; for early mornings, 9 pm the night before): the family
                     sees what's coming and can change it. Their changes are in place before the cook hears.
    VISIT_BRIEF      at the start of each visit: what to make, for whom, tweaks, prep for next time.
                     Sent as a text and a voice note.
    COOK_CHAT        whenever the cook replies (text or voice): the cook agent handles it (agent.run_cook_turn).
    WRAP_UP          at the end of each visit: anything finished, left over, how it went.

Events follow the cook's visits on the simulated clock. `advance()` jumps to the next one for demos.
Every message is sent at most once (the `sent` table).
"""

import datetime as dt
import sqlite3
from pathlib import Path

from pydantic import Field

from app import bridge, clock, llm, queries, speech, telegram
from app.db import db
from app.models import CookVisit, Model

PROMPTS = Path(__file__).parent / "prompts"


class Brief(Model):
    message: str = Field(description="Greeting, the menu, any per-person tweak, prep for next time, an invite to reply. "
                                     "Four to six short lines. Never recipe steps.")


CHECK_LEAD = dt.timedelta(hours=2)
EARLIEST_CHECK = dt.time(8, 0)  # never message the family before this; check the night before instead
NIGHT_BEFORE = dt.time(21, 0)


class Event(Model):
    at: dt.datetime
    kind: str  # "check" | "brief" | "wrap_up"
    visit: CookVisit | None = None
    key: str


def _events(conn: sqlite3.Connection, days: int = 3) -> list[Event]:
    cook = queries.get_cook(conn)
    today = clock.now(conn).date()
    out = []
    for offset in range(days):
        day = today + dt.timedelta(days=offset)
        if cook is None or cook.household_cooks or day.strftime("%a").lower() in cook.days_off:
            continue
        for visit in cook.visits:
            start = dt.datetime.combine(day, visit.start, clock.IST)
            check = start - CHECK_LEAD
            if check.time() < EARLIEST_CHECK:
                check = dt.datetime.combine(day - dt.timedelta(days=1), NIGHT_BEFORE, clock.IST)
            out.append(Event(at=check, kind="check", visit=visit, key=f"check {day} {visit.label}"))
            out.append(Event(at=start, kind="brief", visit=visit, key=f"brief {day} {visit.label}"))
            out.append(Event(at=start + dt.timedelta(minutes=visit.minutes), kind="wrap_up", visit=visit,
                             key=f"wrap_up {day} {visit.label}"))
    return sorted(out, key=lambda e: e.at)


async def send_brief(conn: sqlite3.Connection, day: dt.date, visit: CookVisit) -> str | None:
    stored = queries.get_plan(conn)
    cook = queries.get_cook(conn)
    meals = [m for m in stored.plan.meals if m.day == day and m.meal in visit.meals] if stored else []
    if not meals:
        return None
    menu = "\n".join(f"{m.meal}: " + "; ".join(f"{d.name} for {bridge.for_cook(conn, d.for_whom)}"
                                              + (f" (note: {d.cook_note})" if d.cook_note else "") for d in m.dishes)
                     for m in meals)
    later = [m for m in bridge.upcoming(conn, stored.plan) if (m.day, m.meal) not in {(x.day, x.meal) for x in meals}][:3]
    brief = await llm.ask(Brief, system=(PROMPTS / "cook_brief.md").read_text(encoding="utf-8"), prompt=(
        f"COOK: {cook.name or 'the cook'}\nVISIT: {day:%A} {visit.label}, {visit.start:%H:%M}, about {visit.minutes} minutes\n"
        f"COOK IS GOOD AT: {', '.join(cook.known_dishes) or 'not noted'}\nCOOK NOTES: {cook.notes or 'none'}\n\n"
        f"MENU FOR THIS VISIT\n{menu}\n\nNEXT MEALS AFTER THIS VISIT\n"
        + "\n".join(bridge.describe(conn, m) for m in later)
        + "\n\nPREP NOTES FOR THE WEEK (mention one only if it's for one of the NEXT MEALS above and must be "
          "done on this visit; never prep for a meal that has passed)\n" + "\n".join(stored.plan.prep_ahead)))
    await bridge.tell_cook(conn, brief.message, voice=True)
    return brief.message


async def send_wrap_up(conn: sqlite3.Connection, visit: CookVisit) -> str:
    cook = queries.get_cook(conn)
    text = (f"Thank you {cook.name or 'ji'}! Before you go: anything finished or running low, anything left over, "
            "and did everyone eat well? Just reply here.")
    await bridge.tell_cook(conn, text, voice=False)
    return text


def send_check(conn: sqlite3.Connection, day: dt.date, visit: CookVisit) -> str | None:
    """Before a visit: show the family what's coming, so a change happens before the cook is briefed."""
    stored = queries.get_plan(conn)
    cook = queries.get_cook(conn)
    meals = [m for m in stored.plan.meals if m.day == day and m.meal in visit.meals] if stored else []
    if not meals:
        return None
    when = bridge.when(conn, day)
    menu = "; ".join(f"{m.meal} is " + " and ".join(d.name for d in m.dishes) for m in meals)
    text = (f"Coming up: {cook.name or 'the cook'}'s {visit.label} visit {when}. {menu[0].upper() + menu[1:]}. "
            "Want to change anything before I brief them?")
    bridge.tell_family(conn, text)
    return text


def _visit_day(event: Event) -> dt.date:
    """A check can happen the night before; the visit it's about is in its key ("check 2026-10-17 morning")."""
    return dt.date.fromisoformat(event.key.split()[1])


async def advance() -> dict:
    """Jump the simulated clock to the cook's next visit event and run it (brief or wrap-up)."""
    with db() as conn:
        now = clock.now(conn)
        upcoming = [e for e in _events(conn) if e.at > now]
        if not upcoming:
            return {"now": now.isoformat(), "event": None}
        event = upcoming[0]
        clock.set_now(conn, event.at)
        if not queries.mark_sent(conn, event.key):
            return {"now": event.at.isoformat(), "event": event.key, "sent": None}
        visit_day = event.at.date() if event.kind != "check" else _visit_day(event)
        if event.kind == "check":
            sent = send_check(conn, visit_day, event.visit)
        elif event.kind == "brief":
            sent = await send_brief(conn, visit_day, event.visit)
        else:
            sent = await send_wrap_up(conn, event.visit)
    return {"now": event.at.isoformat(), "event": event.key, "sent": sent}


async def on_telegram_message(incoming: telegram.Incoming) -> None:
    """A message from someone who linked their number. If it's the cook, the cook agent answers."""
    from app.agent import run_cook_turn  # the agent imports the flow, which imports these tools

    with db() as conn:
        cook = queries.get_cook(conn)
    if not cook or not cook.phone or telegram.normalize(cook.phone) != incoming.contact.phone:
        return
    text = incoming.text or ""
    if incoming.voice_file_id:
        try:
            audio = await telegram.download(incoming.voice_file_id)
            text = speech.stt(audio, content_type=speech.OGG_OPUS) or text
        except (telegram.TelegramError, speech.SpeechError):
            pass
    if not text.strip():
        await telegram.send(cook.phone, "Sorry, I couldn't hear that one. Could you type it?")
        return
    reply = await run_cook_turn(text)
    await telegram.send(cook.phone, reply or "Got it, thank you! I'll check and get back to you. 🙏")
