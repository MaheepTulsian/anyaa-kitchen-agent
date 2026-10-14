"""Household profile as compact text (for the LLM and read-backs) and onboarding gaps."""

import sqlite3

from app.integrations import instamart_mcp, swiggy_oauth
from app.models import Model, Preference
from app.store import cook, households, members, pantry, preferences


class OnboardingGaps(Model):
    required: list[str]
    optional: list[str]


def _pref_line(pref: Preference) -> str:
    strict = " [STRICT]" if pref.strict else ""
    return f"  #{pref.id} {pref.category}{strict}: {pref.detail} (\"{pref.quote}\")"


def render_profile(conn: sqlite3.Connection, household_id: int) -> str:
    household = households.ensure_household(conn, household_id)
    people = members.list_members(conn, household_id)
    prefs = preferences.list_preferences(conn, household_id)
    cook_profile = cook.get_cook_profile(conn, household_id)
    stock = pantry.list_pantry(conn, household_id)

    meals = ", ".join(m.value for m in household.meals) if household.meals_set else "not set yet"
    lines = [f"HOUSEHOLD · meals planned: {meals}"]

    lines.append("MEMBERS" if people else "MEMBERS: none yet")
    for person in people:
        lines.append(f"- {person.name} ({person.age_group.value}, {person.diet.value}, spice {person.spice_level})")
        lines += [_pref_line(p) for p in prefs if p.member and p.member.lower() == person.name.lower()]

    household_prefs = [p for p in prefs if not p.member]
    if household_prefs:
        lines.append("WHOLE HOUSEHOLD")
        lines += [_pref_line(p) for p in household_prefs]

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
    """Hard minimum to confirm the profile. Topic coverage is driven by the interview prompt."""
    household = households.ensure_household(conn, household_id)
    people = members.list_members(conn, household_id)
    cook_profile = cook.get_cook_profile(conn, household_id)

    required: list[str] = []
    if not people:
        required.append("who eats at home, and whether each person is veg, non-veg, eggetarian or Jain")
    if not household.meals_set:
        required.append("which meals to plan (breakfast, lunch, dinner)")
    if cook_profile is None:
        required.append("the cook's visits (times, minutes, meals) or that the family cooks")

    optional: list[str] = []
    if not pantry.list_pantry(conn, household_id):
        optional.append("staples already in the pantry")
    if swiggy_oauth.load_token() is None:
        optional.append("connect Instamart (Swiggy login)")
    elif instamart_mcp.selected_address() is None:
        optional.append("choose the Instamart delivery address")
    return OnboardingGaps(required=required, optional=optional)
