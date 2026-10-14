"""Household profile as compact text (for the LLM and read-backs) and onboarding gaps."""

import sqlite3

from app.integrations import instamart_mcp, swiggy_oauth
from app.models import Constraint, ConstraintKind, Member, Model
from app.store import constraints, cook, households, members, pantry


class OnboardingGaps(Model):
    required: list[str]
    optional: list[str]


def _member_line(member: Member, rules: list[Constraint]) -> str:
    parts = [f"- {member.name} ({member.age_group.value}, {member.diet.value}, spice {member.spice_level})"]
    if member.relation:
        parts[0] += f" · {member.relation}"
    for rule in rules:
        if rule.kind is ConstraintKind.ALLERGEN:
            label = "allergies: none" if rule.value == "none" else f"ALLERGY {rule.value}, {rule.scope or 'scope unknown'} (HARD)"
        else:
            label = f"{rule.kind.value}: {rule.value}"
            if rule.scope:
                label += f" on {rule.scope}"
            label += f" ({rule.strength.value})"
        if rule.condition:
            label += f" unless {rule.condition}"
        parts.append(f'{label} "{rule.quote}"')
    return " · ".join(parts)


def render_profile(conn: sqlite3.Connection, household_id: int) -> str:
    household = households.ensure_household(conn, household_id)
    people = members.list_members(conn, household_id)
    rules = constraints.list_active_constraints(conn, household_id)
    cook_profile = cook.get_cook_profile(conn, household_id)
    stock = pantry.list_pantry(conn, household_id)

    meals = ", ".join(m.value for m in household.meals) if household.meals_set else "not set yet"
    lines = [f"HOUSEHOLD · meals planned: {meals}"]
    if household.cuisine_prefs:
        lines[0] += f" · cuisines: {', '.join(household.cuisine_prefs)}"

    lines.append("MEMBERS" if people else "MEMBERS: none yet")
    for person in people:
        lines.append(_member_line(person, [r for r in rules if r.member_id == person.id]))

    household_rules = [r for r in rules if r.member_id is None]
    if household_rules:
        lines.append(
            "HOUSEHOLD RULES: "
            + " · ".join(
                f"{r.kind.value} {r.value}{' on ' + r.scope if r.scope else ''}"
                f"{' unless ' + r.condition if r.condition else ''} ({r.strength.value})"
                for r in household_rules
            )
        )

    if cook_profile is None:
        lines.append("COOK: not set yet")
    elif cook_profile.household_cooks:
        lines.append("COOK: none, the family cooks")
    else:
        visits = " · ".join(
            f"{v.label} {v.start.strftime('%H:%M')} ({v.minutes}m: {', '.join(m.value for m in v.meals)})"
            for v in cook_profile.visits
        )
        off = f" · off {', '.join(d.value for d in cook_profile.days_off)}" if cook_profile.days_off else ""
        known = f" · makes well: {', '.join(cook_profile.known_dishes)}" if cook_profile.known_dishes else ""
        lines.append(f"COOK: {cook_profile.name or 'unnamed'} · {visits}{off}{known}")

    if stock:
        lines.append("PANTRY: " + ", ".join(f"{p.item} {p.qty:g}{p.unit.value}" for p in stock))
    return "\n".join(lines)


def onboarding_gaps(conn: sqlite3.Connection, household_id: int) -> OnboardingGaps:
    household = households.ensure_household(conn, household_id)
    people = members.list_members(conn, household_id)
    rules = constraints.list_active_constraints(conn, household_id)
    cook_profile = cook.get_cook_profile(conn, household_id)

    required: list[str] = []
    if not people:
        required.append("who eats at home (names, rough age, veg/non-veg)")
    for person in people:
        if not any(r.member_id == person.id and r.kind is ConstraintKind.ALLERGEN for r in rules):
            required.append(f"allergy answer for {person.name} (store allergen 'none' if none)")
    if not household.meals_set:
        required.append("which meals to plan (breakfast, lunch, dinner)")
    if cook_profile is None:
        required.append("the cook's visits (times, minutes, meals) or that the family cooks")

    optional: list[str] = []
    if not any(r.kind is ConstraintKind.FAVOURITE for r in rules):
        optional.append("favourite dishes")
    if not any(r.kind in (ConstraintKind.DISLIKE_DISH, ConstraintKind.AVOID_INGREDIENT) for r in rules):
        optional.append("dislikes or things to avoid")
    if cook_profile and not cook_profile.household_cooks and not cook_profile.known_dishes:
        optional.append("dishes the cook already makes well")
    if not pantry.list_pantry(conn, household_id):
        optional.append("staples already in the pantry")
    if swiggy_oauth.load_token() is None:
        optional.append("connect Instamart (Swiggy login)")
    elif instamart_mcp.selected_address() is None:
        optional.append("choose the Instamart delivery address")
    return OnboardingGaps(required=required, optional=optional)
