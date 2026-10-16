"""MEAL_PLAN node tools: agree today and tomorrow, then the whole week. Nothing else."""

import datetime as dt

from pydantic import Field

from app import clock, planner, queries
from app.db import db
from app.models import Model, Phase, StoredPlan
from app.tools import ToolError, anyaa_tool
from app.tools.onboarding import add_preferences, remove_preference


class NoInput(Model):
    pass


class ChangeInput(Model):
    request: str = Field(description='The change in their words: "no rajma tomorrow", "2 guests for Sunday lunch".')


def _when(day: dt.date, today: dt.date) -> str:
    """Say days the way people do, so "tomorrow's breakfast" is never called "tonight"."""
    if day == today:
        return f"today ({day:%a})"
    if day == today + dt.timedelta(days=1):
        return f"tomorrow ({day:%a})"
    return f"{day:%A}"


def _summary(stored: StoredPlan) -> dict:
    """What you need to talk about the plan; the full plan is on their screen."""
    plan = stored.plan
    with db() as conn:
        now = clock.now(conn)
    return {
        "now": f"{now:%A %H:%M}",
        "stage": stored.stage,
        "meals": [f"{_when(m.day, now.date())} {m.meal}: " + " + ".join(f"{d.name} ({', '.join(d.for_whom)})" for d in m.dishes)
                  for m in plan.meals],
        "cook_notes": [f"{_when(m.day, now.date())} {m.meal}, {d.name}: {d.cook_note}"
                       for m in plan.meals for d in m.dishes if d.cook_note],
        "why": [f"{_when(m.day, now.date())} {m.meal}: {m.why}" for m in plan.meals],
        "prep_ahead": plan.prep_ahead,
        "notes_for_family": plan.notes_for_family,
        "safety": "all clear" if not stored.issues else [i.problem for i in stored.issues],
    }


def _current() -> StoredPlan:
    with db() as conn:
        stored = queries.get_plan(conn)
    if stored is None:
        raise ToolError("there's no plan yet", "Call get_near_plan first.")
    return stored


@anyaa_tool("get_near_plan", "Today's remaining meals and tomorrow's, to discuss first. Can take up to a minute.", NoInput)
async def get_near_plan(_: NoInput) -> dict:
    with db() as conn:
        return _summary(await planner.first_plan(conn))


@anyaa_tool("change_plan", "Change the current plan the way they asked. Only the days it touches are redone.", ChangeInput)
async def change_plan(args: ChangeInput) -> dict:
    stored = _current()
    with db() as conn:
        return _summary(await planner.change(conn, stored, args.request))


@anyaa_tool("plan_the_week", "Call once they've agreed today and tomorrow: keeps those, plans the rest of the week. Takes a minute.", NoInput)
async def plan_the_week(_: NoInput) -> dict:
    stored = _current()
    if stored.stage == "week":
        raise ToolError("the week is already planned", "Talk about it, or use change_plan.")
    if stored.issues:
        raise ToolError("today/tomorrow still have safety problems", "Fix them with change_plan first.")
    with db() as conn:
        return _summary(await planner.extend_to_week(conn, stored))


@anyaa_tool("agree_week_plan", "Call only after they said yes to the whole week. Locks it in.", NoInput)
def agree_week_plan(_: NoInput) -> dict:
    stored = _current()
    if stored.stage != "week":
        raise ToolError("only today and tomorrow are planned", "Agree those, then call plan_the_week first.")
    if stored.issues:
        raise ToolError("the week still has safety problems", "Fix them with change_plan first.")
    with db() as conn:
        queries.save_plan(conn, stored.model_copy(update={"status": "agreed"}))
        queries.set_phase(conn, Phase.GROCERIES)
    return {"agreed": True}


MEAL_PLAN_TOOLS = [get_near_plan, change_plan, plan_the_week, agree_week_plan, add_preferences, remove_preference]
