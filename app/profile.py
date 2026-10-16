"""The household profile as compact text: what the agent sees in <context>, and the read-back."""

import sqlite3

from app import queries
from app.models import Preference


def _note(p: Preference) -> str:
    strict = " [STRICT]" if p.strict else ""
    return f'  #{p.id} {p.category}{strict}: {p.detail} ("{p.quote}")'


def render(conn: sqlite3.Connection) -> str:
    household = queries.get_household(conn)
    people = queries.list_members(conn)
    everything = queries.list_preferences(conn)
    parked = [p for p in everything if p.category == "parked"]
    notes = [p for p in everything if p.category != "parked"]
    cook = queries.get_cook(conn)
    pantry = queries.list_pantry(conn)

    meals = ", ".join(household.meals) if household.meals_set else "not set yet"
    lines = [f"MEALS PLANNED: {meals}", "MEMBERS" if people else "MEMBERS: none yet"]
    for person in people:
        diet = person.diet if person.diet_confirmed else f"{person.diet}? (guessed, not confirmed)"
        lines.append(f"- {person.name} ({person.age_group}, {diet}, spice {person.spice_level}/4)")
        lines += [_note(p) for p in notes if (p.member or "").lower() == person.name.lower()]

    if parked:
        lines += ["PARKED (said earlier, belongs to a later part: save it properly in the right part, then remove it)",
                  *(f"  #{p.id} about {p.member or 'the household'}: {p.detail} (\"{p.quote}\")" for p in parked)]
    if household_notes := [p for p in notes if not p.member]:
        lines += ["WHOLE HOUSEHOLD", *map(_note, household_notes)]

    if cook is None:
        lines.append("COOK: not set yet")
    elif cook.household_cooks:
        lines.append("COOK: none, the family cooks")
    else:
        visits = " · ".join(f"{v.label} {v.start:%H:%M} for {v.minutes} min ({', '.join(v.meals)})" for v in cook.visits)
        lines.append(f"COOK: {cook.name or 'unnamed'} · {visits}")
        lines.append(f"  phone: {cook.phone}" if cook.phone else "  phone: not given yet")
        if cook.days_off:
            lines.append(f"  off on {', '.join(cook.days_off)}")
        if cook.known_dishes:
            lines.append(f"  makes well: {', '.join(cook.known_dishes)}")

    if pantry:
        lines.append("PANTRY: " + ", ".join(f"{p.item} {p.qty:g}{p.unit}" for p in pantry))
    return "\n".join(lines)


DIET_WORDS = {"veg": "is vegetarian", "eggetarian": "eats eggs but no meat", "nonveg": "eats non-veg",
              "jain": "is Jain (no onion, garlic or root vegetables)", "vegan": "is vegan"}


def facts(conn: sqlite3.Connection) -> list[str]:
    """The profile as plain sentences, made in code, so a spoken summary can't get them wrong."""
    out = [f"{m.name} {DIET_WORDS[m.diet]}" for m in queries.list_members(conn)]
    notes = [p for p in queries.list_preferences(conn) if p.category != "parked" and p.detail.lower() != "none"]
    out += [f"STRICT for {p.member or 'everyone'}: {p.detail}" for p in notes if p.strict]
    out += [f"{p.member or 'Household'} ({p.category}): {p.detail}" for p in notes if not p.strict]
    cook = queries.get_cook(conn)
    if cook and cook.household_cooks:
        out.append("The family cooks; no hired cook")
    elif cook:
        out.append(f"{cook.name or 'The cook'} comes " + " and ".join(
            f"{v.label} at {v.start:%-I:%M %p} for {', '.join(v.meals)}" for v in cook.visits))
    household = queries.get_household(conn)
    if household.meals_set:
        out.append(f"Meals planned: {', '.join(household.meals)}")
    return out
