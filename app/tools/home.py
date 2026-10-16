"""Household tools after the plan is agreed: GROCERIES (fill the cart) and RUNNING (everyday mode)."""

import datetime as dt

from pydantic import Field

from app import bridge, cart, clock, planner, queries
from app.db import db
from app.models import GroceryLine, Model, Phase
from app.tools import ToolError, anyaa_tool
from app.tools.onboarding import add_preferences, remove_preference


class NoInput(Model):
    pass


class DoneInput(Model):
    cart_filled: bool = Field(description="true if the cart was filled; false if they said not now.")


class DayInput(Model):
    day: str = Field(description='"today", "tomorrow", or a weekday like "saturday".')


class ChangeInput(Model):
    request: str = Field(description='The change in their words: "no rajma tomorrow", "eating out Saturday night".')


class AnswerInput(Model):
    question_id: int
    choice: str = Field(description='"a" or "b"')


def _restock(conn) -> list[GroceryLine]:
    """Things the cook said ran out; they go on the next list."""
    return [GroceryLine(item=p.detail, quantity="1", where="instamart")
            for p in queries.list_preferences(conn) if p.category == "restock"]


# --- GROCERIES --------------------------------------------------------------------------------


@anyaa_tool("grocery_list", "The week's shopping list, split into Instamart and sabziwala, after the pantry.", NoInput)
async def grocery_list(_: NoInput) -> dict:
    with db() as conn:
        stored = queries.get_plan(conn)
        if stored is None or stored.stage != "week":
            raise ToolError("there's no agreed week plan", "This shouldn't happen; tell them the plan comes first.")
        stored = await planner.groceries(conn, stored)
        restock = _restock(conn)
    lines = stored.plan.groceries + restock
    instamart = [f"{g.item} {g.quantity}" for g in lines if g.where == "instamart"]
    sabziwala = [f"{g.item} {g.quantity}" for g in lines if g.where == "sabziwala"]
    return {"instamart": instamart, "sabziwala": sabziwala}


@anyaa_tool("fill_cart", "Only after they said yes: fills their Instamart cart (replacing what's in it). Never orders.", NoInput)
async def fill_cart(_: NoInput) -> dict:
    with db() as conn:
        stored = queries.get_plan(conn)
        if stored is None:
            raise ToolError("no plan", "Agree the plan first.")
        plan = stored.plan.model_copy(update={"groceries": stored.plan.groceries + _restock(conn)})
        summary = await cart.fill(conn, plan)
        queries.save_plan(conn, stored.model_copy(update={"cart": summary.model_dump()}))
    return {"cart": f"{len(summary.items)} items, about ₹{summary.total:.0f}", "mode": summary.mode,
            "sabziwala_items": len(summary.sabziwala), "sabziwala_link": "on their screen"}


@anyaa_tool("groceries_done", "Call after the cart is filled, or after they said not now.", DoneInput)
def groceries_done(args: DoneInput) -> dict:
    with db() as conn:
        queries.set_phase(conn, Phase.RUNNING)
    return {"done": True, "next": "The next part starts on its own. Don't say anything more this turn."}


# --- RUNNING ----------------------------------------------------------------------------------


def _day(text: str, today: dt.date) -> dt.date:
    text = text.strip().lower()
    if text in ("today", "tonight"):
        return today
    if text == "tomorrow":
        return today + dt.timedelta(days=1)
    for ahead in range(7):
        day = today + dt.timedelta(days=ahead)
        if day.strftime("%A").lower().startswith(text[:3]):
            return day
    raise ToolError(f"don't know which day '{text}' is", 'Use "today", "tomorrow" or a weekday name.')


@anyaa_tool("whats_planned", "The meals planned for one day.", DayInput)
def whats_planned(args: DayInput) -> dict:
    with db() as conn:
        stored = queries.get_plan(conn)
        day = _day(args.day, clock.now(conn).date())
    if stored is None:
        raise ToolError("no plan yet", "Tell them the plan comes first.")
    meals = [m for m in stored.plan.meals if m.day == day]
    return {"day": f"{day:%A %d %B}", "meals": [f"{m.meal}: " + " + ".join(d.name for d in m.dishes) for m in meals]
            or ["nothing planned that day"]}


@anyaa_tool("change_week_plan", "Change the agreed plan the way they asked. Only affected days are redone.", ChangeInput)
async def change_week_plan(args: ChangeInput) -> dict:
    with db() as conn:
        stored = queries.get_plan(conn)
        if stored is None:
            raise ToolError("no plan yet", "Tell them the plan comes first.")
        changed = await planner.change(conn, stored, args.request)
        if changed.issues:
            queries.save_plan(conn, stored)  # keep the agreed plan, not the unsafe draft
            return {"changed": False, "safety_problems": [i.problem for i in changed.issues]}
        queries.save_plan(conn, changed.model_copy(update={"status": "agreed"}))
        return {"changed": True, **await bridge.family_changed(conn, stored.plan, changed.plan)}


@anyaa_tool("answer_cook_question", "Apply the family's A or B answer to a question from the cook side.", AnswerInput)
async def answer_cook_question(args: AnswerInput) -> dict:
    with db() as conn:
        open_ones = {e.id: e for e in queries.open_escalations(conn)}
        if args.question_id not in open_ones:
            raise ToolError("no open question with that id", "Check the open questions in the context.")
        esc = open_ones[args.question_id]
        choice = args.choice.strip().lower()[:1]
        if choice not in ("a", "b"):
            raise ToolError("choice must be a or b", "Ask them to pick one of the two.")
        picked = esc.option_a if choice == "a" else esc.option_b
        queries.resolve_escalation(conn, esc.id, choice)
        stored = queries.get_plan(conn)
        meals = []
        if stored:
            changed = await planner.change(conn, stored, f"{esc.question} The family chose: {picked}. Change only "
                                                         "what this needs; keep every other meal exactly as it is.")
            if changed.issues:
                queries.save_plan(conn, stored)
            else:
                queries.save_plan(conn, changed.model_copy(update={"status": "agreed"}))
                meals = [bridge.describe(conn, m) for m in bridge.changed_meals(stored.plan, changed.plan)
                         if bridge.is_upcoming(conn, m)]
        told = await bridge.tell_cook(conn, f"The family says: {picked}." + (f" So {'; '.join(meals)}." if meals else ""))
    return {"applied": picked, "changed_meals": meals, "cook_told": told}


GROCERIES_TOOLS = [grocery_list, fill_cart, groceries_done]
RUNNING_TOOLS = [whats_planned, change_week_plan, answer_cook_question, grocery_list, fill_cart, add_preferences,
                 remove_preference]
