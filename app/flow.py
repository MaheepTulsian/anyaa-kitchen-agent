"""The household agent's flow: every node, what it may do, what it sees, and which one is active.

    household:  FAMILY → FOOD_NEEDS → TASTES → KITCHEN → CONFIRM → MEAL_PLAN → GROCERIES → RUNNING
    cook:       COOK_CHAT (Telegram replies); briefs and wrap-ups are sent on the clock (cook.py)

A node = system prompt files + its own tools + the live data it sees + an opener (it speaks first).
Which node is active is stored in the database and changed only by a node's `*_done` tool, after
its requirements are checked in code. The model can't skip a node or use another node's tools.
"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import re

from app import bridge, profile, queries
from app.models import Agent, Phase
from app.tools.onboarding import CONFIRM_TOOLS, FAMILY_TOOLS, KITCHEN_TOOLS, NEEDS_TOOLS, TASTES_TOOLS
from app.tools.cook import COOK_TOOLS
from app.tools.home import GROCERIES_TOOLS, RUNNING_TOOLS
from app.tools.plan import MEAL_PLAN_TOOLS

PROMPTS = Path(__file__).parent / "prompts"
ONBOARDING = ["household_persona.md", "onboarding_rules.md"]


@dataclass
class Node:
    name: str
    prompts: list[str]  # files in app/prompts/, joined into the system prompt
    tools: list[Any]  # the only tools this node can call
    context: Callable[[sqlite3.Connection], str]  # live data attached to every message
    scope: str = ""  # one line, repeated at the end of every message: what this node may talk about
    opener: str = "[start] Open this part now. Say only your opening, nothing from the context."
    hint: Callable[[str], str | None] | None = None  # a nudge added to the message for answers we can recognise
    agent: Agent = Agent.HOUSEHOLD

    def system_prompt(self) -> str:
        return "\n\n".join((PROMPTS / name).read_text(encoding="utf-8") for name in self.prompts)


def plan_context(conn: sqlite3.Connection) -> str:
    stored = queries.get_plan(conn)
    state = "not made yet" if stored is None else f"{stored.stage} plan, {stored.status}"
    return f"{profile.render(conn)}\nPLAN: {state}"


def running_context(conn: sqlite3.Connection) -> str:
    questions = queries.open_escalations(conn)
    open_qs = "\n".join(f"  question {e.id}: {e.question} (A) {e.option_a} (B) {e.option_b}" for e in questions)
    kitchen = bridge.recent(conn, Agent.COOK, 4)
    return (f"{plan_context(conn)}\nOPEN QUESTIONS FOR THE FAMILY\n{open_qs or '  none'}\n"
            f"LATEST WITH THE COOK (last 24 h)\n" + ("\n".join(f"  {line}" for line in kitchen) or "  nothing") + "\n"
            f"LATEST IN THIS CHAT (you may have sent some of these outside the conversation)\n"
            + "\n".join(f"  {line}" for line in bridge.recent(conn, Agent.HOUSEHOLD, 4)))


def cook_context(conn: sqlite3.Connection) -> str:
    """What the cook agent sees: the cook and the menu. Never the family's health notes."""
    cook = queries.get_cook(conn)
    stored = queries.get_plan(conn)
    lines = [f"COOK: {cook.name if cook else 'the cook'}"]
    if cook and not cook.household_cooks:
        lines.append("VISITS: " + " · ".join(f"{v.label} {v.start:%H:%M} for {v.minutes} min ({', '.join(v.meals)})"
                                             for v in cook.visits))
    if stored:
        lines.append("NEXT MEALS (not cooked yet; the first one is what they're making now or next)")
        lines += [f"  {bridge.describe(conn, m)}" + "".join(f" | {d.cook_note}" for d in m.dishes if d.cook_note)
                  for m in bridge.upcoming(conn, stored.plan)[:3]]
    waiting = queries.open_escalations(conn)
    lines.append("WAITING ON THE FAMILY: " + ("; ".join(e.question for e in waiting) if waiting else "nothing"))
    lines.append("LATEST IN THIS CHAT (your briefs and updates are sent outside the conversation)")
    lines += [f"  {line}" for line in bridge.recent(conn, Agent.COOK, 6)]
    return "\n".join(lines)


YES = re.compile(r"^\s*(yes|yeah|yep|yup|ok+|okay|haan|han|ha|sure|go ahead|do it|fine|theek hai|done|👍)\b", re.I)


def groceries_hint(text: str) -> str | None:
    if YES.search(text):
        return "They said yes. Call fill_cart now. You can't know whether it works until it returns."
    return None


CART = re.compile(r"\b(cart|instamart|order (the )?groceries|order (it|them|this))\b", re.I)


def running_hint(text: str) -> str | None:
    if CART.search(text):
        return "They want the cart filled. Call fill_cart now. You can't know whether it works until it returns."
    return None


PARK = "Anything else they mention: park it with park_for_later, say 'noted for later', and stay on topic."

HOUSEHOLD_NODES = {
    Phase.FAMILY: Node(
        "FAMILY", [*ONBOARDING, "nodes/family.md"], FAMILY_TOOLS, profile.render,
        scope=f"Only ask who eats at home and each person's diet (veg, non-veg, eggetarian, Jain). "
              f"No allergies, health, tastes, cook or meals. No recaps. {PARK}"),
    Phase.FOOD_NEEDS: Node(
        "FOOD_NEEDS", [*ONBOARDING, "nodes/food_needs.md"], NEEDS_TOOLS, profile.render,
        scope=f"Only allergies, intolerances, health needs, never-eat foods, fasting. Sort any parked notes on "
              f"these first. No tastes, cook, meals, names or recaps. {PARK}"),
    Phase.TASTES: Node(
        "TASTES", [*ONBOARDING, "nodes/tastes.md"], TASTES_TOOLS, profile.render,
        scope=f"Only everyday food, favourites, dislikes, spice. Sort any parked notes on these first. "
              f"No cook, meals to plan or recaps. {PARK}"),
    Phase.KITCHEN: Node(
        "KITCHEN", [*ONBOARDING, "nodes/kitchen.md"], KITCHEN_TOOLS, profile.render,
        scope=f"Only the cook (name, visits, days off, strengths, phone) and which meals to plan. Sort any parked "
              f"cook notes into the cook profile first. No recaps. {PARK}"),
    Phase.CONFIRM: Node(
        "CONFIRM", [*ONBOARDING, "nodes/confirm.md"], CONFIRM_TOOLS, profile.render,
        scope="Sort every parked note into a proper note (or remove it), give the short summary, ask what's "
              "missing, confirm on a yes. Nothing else."),
    Phase.MEAL_PLAN: Node(
        "MEAL_PLAN", ["household_persona.md", "nodes/meal_plan.md"], MEAL_PLAN_TOOLS, plan_context,
        scope="Only agreeing the meals: today and tomorrow first, then the week. When they reject something, "
              "pick the replacement yourself. Save rule-like feedback as a note before changing the plan."),
    Phase.GROCERIES: Node(
        "GROCERIES", ["household_persona.md", "nodes/groceries.md"], GROCERIES_TOOLS, plan_context,
        scope="Only the week's groceries: summarise, fill the cart on a yes, point to the sabziwala list. Never order.",
        hint=groceries_hint),
    Phase.RUNNING: Node(
        "RUNNING", ["household_persona.md", "nodes/running.md"], RUNNING_TOOLS, running_context,
        scope="Everyday mode: answer, change the plan when asked, apply answers to open questions. Short.",
        hint=running_hint),
}

COOK_NODE = Node(
    "COOK_CHAT", ["cook_persona.md", "nodes/cook_chat.md"], COOK_TOOLS, cook_context, agent=Agent.COOK,
    scope="Only today's cooking. Use tools before answering. Never mention health or reasons. Short.")


def household_node(conn: sqlite3.Connection) -> Node | None:
    return HOUSEHOLD_NODES.get(queries.get_household(conn).phase)
