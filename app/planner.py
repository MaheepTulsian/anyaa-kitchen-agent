"""Meal planning: fast structured steps, a separate safety check, and awareness of the time.

    stored = await planner.plan_near(conn)                       # today's remaining meals + tomorrow
    stored = await planner.change(conn, stored, "no rajma")      # only the touched days are redone
    stored = await planner.extend_to_week(conn, stored)          # agreed days kept, the rest planned

Each plan is made in steps so it's quick:
1. Sketch:   one small call decides what's cooked for whom on every day (keeps variety).
2. Details:  one call per day, in parallel: ingredients, cook notes, the "why".
3. Safety:   a separate call compares every dish with every person's strict notes and diet;
             unsafe days are rewritten (at most twice). Groceries are written for the full week only.
"""

import asyncio
import datetime as dt
import sqlite3
from pathlib import Path

from app import clock, llm, profile, queries
from app.db import db
from app.models import (
    DayDetail,
    GroceryList,
    Meal,
    MealPlan,
    MenuSketch,
    PlannedMeal,
    SafetyIssue,
    SafetyReport,
    StoredPlan,
)

PROMPTS = Path(__file__).parent / "prompts"
MAX_FIXES = 2
WEEK_DAYS = 7
DEFAULT_TIMES = {Meal.BREAKFAST: dt.time(8, 0), Meal.LUNCH: dt.time(13, 0), Meal.DINNER: dt.time(20, 0)}
LEAD = dt.timedelta(minutes=30)  # a meal can still be planned if it starts at least this far away

Slots = list[tuple[dt.date, list[Meal]]]


def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def _order(meal: PlannedMeal) -> tuple:
    return meal.day, list(Meal).index(meal.meal)


# --- which meals to plan, given the time --------------------------------------------------------


def _meal_time(conn: sqlite3.Connection, meal: Meal, day: dt.date) -> dt.time:
    """When this meal gets cooked: the start of the cook visit that covers it, else a usual time."""
    cook = queries.get_cook(conn)
    if cook and not cook.household_cooks and day.strftime("%a").lower() not in cook.days_off:
        for visit in cook.visits:
            if meal in visit.meals:
                return visit.start
    return DEFAULT_TIMES[meal]


def _slots(conn: sqlite3.Connection, days: int) -> Slots:
    """The next `days` days that have meals left to plan. Today only counts meals not yet cooked."""
    now = clock.now(conn)
    meals = queries.get_household(conn).meals
    out: Slots = []
    day = now.date()
    while len(out) < days:
        left = [m for m in meals if day > now.date()
                or dt.datetime.combine(day, _meal_time(conn, m, day), now.tzinfo) - now >= LEAD]
        if left:
            out.append((day, left))
        day += dt.timedelta(days=1)
    return out


def _describe(conn: sqlite3.Connection, slots: Slots) -> str:
    now = clock.now(conn)
    cook = queries.get_cook(conn)
    lines = [f"It is now {now:%A %d %B, %H:%M}."]
    for day, meals in slots:
        label = "TODAY" if day == now.date() else "TOMORROW" if day == now.date() + dt.timedelta(days=1) else f"{day:%A}"
        if cook is None or cook.household_cooks:
            who = "the family cooks"
        elif day.strftime("%a").lower() in cook.days_off:
            who = f"{cook.name or 'the cook'} is OFF, the family cooks (keep it quick)"
        else:
            who = " · ".join(f"{cook.name or 'cook'} {v.label} {v.start:%H:%M}, {v.minutes} min for "
                             f"{', '.join(m for m in v.meals if m in meals) or 'nothing today'}" for v in cook.visits)
        lines.append(f"- {day.isoformat()} ({label}): plan {', '.join(meals)} · {who}")
    return "\n".join(lines)


# --- the LLM steps ----------------------------------------------------------------------------


async def _sketch(base: str, ask: str) -> MenuSketch:
    return await llm.ask(MenuSketch, system=_prompt("planner.md"), prompt=f"{base}\n\n{ask}")


async def _detail(base: str, sketch: MenuSketch, day: dt.date, fix: str = "") -> list[PlannedMeal]:
    todays = MenuSketch(meals=[m for m in sketch.meals if m.day == day]).model_dump_json(include={"meals"})
    ask = f"{base}\n\nWRITE THE FULL DETAIL FOR {day} ONLY, keeping exactly these dishes and eaters:\n{todays}"
    if fix:
        ask += f"\n\nFIX THESE SAFETY PROBLEMS (you may swap a dish for a safe one):\n{fix}"
    return (await llm.ask(DayDetail, system=_prompt("planner.md"), prompt=ask)).meals


async def _check(conn: sqlite3.Connection, meals: list[PlannedMeal]) -> list[SafetyIssue]:
    plan = MealPlan(meals=meals).model_dump_json(include={"meals"})
    report = await llm.ask(SafetyReport, system=_prompt("safety_check.md"),
                           prompt=f"HOUSEHOLD\n{profile.render(conn)}\n\nPLAN\n{plan}")
    return report.issues


async def _details_checked(conn: sqlite3.Connection, base: str, sketch: MenuSketch,
                           days: list[dt.date], kept: list[PlannedMeal]) -> tuple[list[PlannedMeal], list[SafetyIssue]]:
    """Write the given days in parallel, then check everything and rewrite unsafe days."""
    written = await asyncio.gather(*(_detail(base, sketch, day) for day in days))
    meals = sorted(kept + [m for day in written for m in day], key=_order)
    issues = await _check(conn, meals)
    for _ in range(MAX_FIXES):
        if not issues:
            break
        bad = sorted({i.day for i in issues})
        fixes = await asyncio.gather(*(_detail(base, sketch, day, "\n".join(
            f"- {i.meal}, {i.dish}: {i.problem}" for i in issues if i.day == day)) for day in bad))
        meals = sorted([m for m in meals if m.day not in bad] + [m for day in fixes for m in day], key=_order)
        issues = await _check(conn, meals)
    return meals, issues


def _base(conn: sqlite3.Connection, slots: Slots) -> str:
    return f"HOUSEHOLD\n{profile.render(conn)}\n\nDAYS TO PLAN\n{_describe(conn, slots)}"


# --- the three things the MEAL_PLAN node does ---------------------------------------------------


async def plan_near(conn: sqlite3.Connection) -> StoredPlan:
    """Today's remaining meals and tomorrow: the part worth discussing first."""
    slots = _slots(conn, 2)
    base = _base(conn, slots)
    sketch = await _sketch(base, "RETURN ONLY THE MENU SKETCH for these days: the dishes for every meal, and who eats each.")
    meals, issues = await _details_checked(conn, base, sketch, [day for day, _ in slots], kept=[])
    stored = StoredPlan(plan=MealPlan(meals=meals, prep_ahead=sketch.prep_ahead, notes_for_family=sketch.notes_for_family),
                        stage="near", issues=issues)
    queries.save_plan(conn, stored)
    return stored


async def change(conn: sqlite3.Connection, stored: StoredPlan, request: str) -> StoredPlan:
    """Apply the family's change. Only the days whose dishes changed are written again."""
    days = sorted({m.day for m in stored.plan.meals})
    slots = [(d, [m.meal for m in stored.plan.meals if m.day == d]) for d in days]
    base = _base(conn, slots)
    sketch = await _sketch(base, f"CURRENT PLAN\n{stored.plan.model_dump_json(include={'meals'})}\n\n"
                                 f"THE FAMILY ASKED: {request}\nReturn the full sketch, changing only what they asked.")

    def names(meals: list) -> dict[dt.date, list[str]]:
        out: dict[dt.date, list[str]] = {}
        for m in meals:
            out.setdefault(m.day, []).extend(f"{m.meal}:{d.name}" for d in m.dishes)
        return out

    old, new = names(stored.plan.meals), names(sketch.meals)
    redo = [day for day in new if new[day] != old.get(day)]
    kept = [m for m in stored.plan.meals if m.day not in redo]
    meals, issues = await _details_checked(conn, base, sketch, redo, kept)
    plan = stored.plan.model_copy(update={"meals": meals, "prep_ahead": sketch.prep_ahead or stored.plan.prep_ahead})
    updated = stored.model_copy(update={"plan": plan, "issues": issues, "status": "draft"})
    queries.save_plan(conn, updated)
    return updated


async def extend_to_week(conn: sqlite3.Connection, stored: StoredPlan) -> StoredPlan:
    """The agreed days stay exactly as they are; the rest of the week is planned around them."""
    agreed_days = {m.day for m in stored.plan.meals}
    slots = [(day, meals) for day, meals in _slots(conn, WEEK_DAYS) if day not in agreed_days]
    base = _base(conn, slots)
    sketch = await _sketch(base, f"ALREADY AGREED (don't repeat these dishes, keep variety across the week)\n"
                                 f"{stored.plan.model_dump_json(include={'meals'})}\n\n"
                                 "RETURN ONLY THE MENU SKETCH for the days to plan above.")
    meals, issues = await _details_checked(conn, base, sketch, [day for day, _ in slots], kept=list(stored.plan.meals))
    plan = MealPlan(meals=meals, prep_ahead=stored.plan.prep_ahead + sketch.prep_ahead,
                    notes_for_family=sketch.notes_for_family)
    week = StoredPlan(plan=plan, stage="week", issues=issues)
    queries.save_plan(conn, week)
    return week


async def groceries(conn: sqlite3.Connection, stored: StoredPlan) -> StoredPlan:
    """The week's shopping list, written once when it's first needed (not while they wait for the plan)."""
    if stored.plan.groceries:
        return stored
    days = sorted({m.day for m in stored.plan.meals})
    base = _base(conn, [(d, [m.meal for m in stored.plan.meals if m.day == d]) for d in days])
    listed = await llm.ask(GroceryList, system=_prompt("planner.md"),
                           prompt=f"{base}\n\nPLAN\n{stored.plan.model_dump_json(include={'meals'})}\n\n"
                                  "WRITE THE GROCERY LIST for this whole plan.")
    updated = stored.model_copy(update={"plan": stored.plan.model_copy(update={"groceries": listed.groceries})})
    queries.save_plan(conn, updated)
    return updated


# --- planning in the background -----------------------------------------------------------------
# Started the moment the profile is confirmed, so the first proposal is ready sooner.

_background: asyncio.Task | None = None


def start_in_background() -> None:
    global _background

    async def run() -> StoredPlan:
        with db() as conn:
            return await plan_near(conn)

    if _background is None or _background.done():
        _background = asyncio.create_task(run())


async def first_plan(conn: sqlite3.Connection) -> StoredPlan:
    """The near plan: wait for the background one if it's running, else plan now."""
    if _background is not None and not _background.done():
        return await _background
    return queries.get_plan(conn) or await plan_near(conn)
