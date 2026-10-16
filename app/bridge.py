"""The link between the family and the cook: whatever one side does, the other hears about.

    family changes a meal  → if the cook was already briefed for it, the cook gets the update now
    cook says X ran out    → the meal is swapped, the family is told what changed, X goes in the cart
    cook says X is low     → X goes in the cart, the family is asked to order
    family answers A or B  → the cook hears the answer and the new menu

Both agents also see the latest messages of their own chat (briefs, checks, heads-ups are sent outside
their turns) and a line or two from the other side, so neither is surprised by the other.
"""

import datetime as dt
import sqlite3

from app import clock, config, queries, speech, telegram
from app.models import Agent, MealPlan, PlannedMeal, Role

MEAL_ORDER = {"breakfast": 0, "lunch": 1, "dinner": 2}


def tell_family(conn: sqlite3.Connection, text: str) -> None:
    queries.add_message(conn, Agent.HOUSEHOLD, Role.ASSISTANT, text)


async def tell_cook(conn: sqlite3.Connection, text: str, voice: bool = False) -> bool:
    """Telegram, kept in the cook conversation. False if the cook isn't reachable."""
    queries.add_message(conn, Agent.COOK, Role.ASSISTANT, text)
    cook = queries.get_cook(conn)
    if not (cook and cook.phone and telegram.enabled()):
        return False
    try:
        if voice:
            await telegram.send_voice(cook.phone, speech.tts_ogg(text, config.AZURE_TTS_VOICE_COOK), caption=text)
        else:
            await telegram.send(cook.phone, text)
        return True
    except (telegram.TelegramError, speech.SpeechError):
        return False


def cook_name(conn: sqlite3.Connection) -> str:
    cook = queries.get_cook(conn)
    return cook.name if cook and cook.name else "The cook"


def when(conn: sqlite3.Connection, day: dt.date) -> str:
    today = clock.now(conn).date()
    return "today" if day == today else "tomorrow" if day == today + dt.timedelta(days=1) else f"{day:%A}"


def for_cook(conn: sqlite3.Connection, names: list[str]) -> str:
    """Who a dish is for, as the cook would say it ("everyone", "Sushil ji")."""
    members = {m.name for m in queries.list_members(conn)}
    if set(names) >= members:
        return "everyone"
    return ", ".join("the house owner" if n == "Me" else f"{n} ji" for n in names)


def describe(conn: sqlite3.Connection, meal: PlannedMeal) -> str:
    """'tonight's dinner: Chana masala + Roti'."""
    label = f"{when(conn, meal.day)}'s {meal.meal}".replace("today's dinner", "tonight's dinner")
    return f"{label}: " + " + ".join(d.name for d in meal.dishes)


def changed_meals(before: MealPlan, after: MealPlan) -> list[PlannedMeal]:
    old = {(m.day, m.meal): [d.name for d in m.dishes] for m in before.meals}
    return [m for m in after.meals if old.get((m.day, m.meal)) != [d.name for d in m.dishes]]


def _visit_for(conn: sqlite3.Connection, meal: PlannedMeal):
    cook = queries.get_cook(conn)
    if not cook or cook.household_cooks:
        return None
    return next((v for v in cook.visits if meal.meal in v.meals), None)


def is_upcoming(conn: sqlite3.Connection, meal: PlannedMeal) -> bool:
    """Not cooked yet: its visit hasn't ended (or, with no cook, the day isn't over)."""
    now = clock.now(conn)
    visit = _visit_for(conn, meal)
    if visit is None:
        return meal.day >= now.date()
    end = dt.datetime.combine(meal.day, visit.start, clock.IST) + dt.timedelta(minutes=visit.minutes)
    return end > now


def upcoming(conn: sqlite3.Connection, plan: MealPlan) -> list[PlannedMeal]:
    return sorted((m for m in plan.meals if is_upcoming(conn, m)), key=lambda m: (m.day, MEAL_ORDER[m.meal]))


def briefed(conn: sqlite3.Connection, meal: PlannedMeal) -> bool:
    """The cook has already been told about this meal (its visit brief went out)."""
    visit = _visit_for(conn, meal)
    return bool(visit) and queries.was_sent(conn, f"brief {meal.day} {visit.label}")


async def family_changed(conn: sqlite3.Connection, before: MealPlan, after: MealPlan) -> dict:
    """After the family changes the plan: if the cook was already briefed for a changed meal, tell them now."""
    changed = [m for m in changed_meals(before, after) if is_upcoming(conn, m)]
    urgent = [m for m in changed if briefed(conn, m)]
    if urgent:
        lines = "; ".join(describe(conn, m) for m in urgent)
        await tell_cook(conn, f"Small change from the family, {cook_name(conn)}: {lines}. Sorry for the change! 🙏")
    return {"changed_meals": [describe(conn, m) for m in changed],
            "cook": "told just now" if urgent else "hears it in the next brief"}


def recent(conn: sqlite3.Connection, agent: Agent, count: int = 6) -> list[str]:
    """The latest messages in one chat, today and yesterday, as 'Cook: …' / 'You: …' lines."""
    since = clock.now(conn) - dt.timedelta(hours=24)
    them = "Cook" if agent == Agent.COOK else "Family"
    messages = [m for m in queries.list_messages(conn, agent) if m.created_at >= since][-count:]
    return [f"{them if m.role == Role.USER else 'You'}: {m.content[:220]}" for m in messages]
