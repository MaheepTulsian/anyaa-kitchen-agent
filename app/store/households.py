"""Household row: phase, meals and profile confirmation."""

import json
import sqlite3

from app import clock
from app.models import Household, Meal, Phase


def _to_model(row: sqlite3.Row) -> Household:
    return Household.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "phase": row["phase"],
            "meals": json.loads(row["meals_json"]),
            "cuisine_prefs": json.loads(row["cuisine_prefs_json"]),
            "profile_confirmed": bool(row["profile_confirmed"]),
            "created_at": row["created_at"],
        }
    )


def get_household(conn: sqlite3.Connection, household_id: int) -> Household | None:
    row = conn.execute("SELECT * FROM household WHERE id = ?", (household_id,)).fetchone()
    return _to_model(row) if row else None


def ensure_household(conn: sqlite3.Connection, household_id: int = 1) -> Household:
    """Return the household, creating an empty one on first use."""
    existing = get_household(conn, household_id)
    if existing is not None:
        return existing
    conn.execute(
        "INSERT INTO household (id, created_at) VALUES (?, ?)",
        (household_id, clock.real_now().isoformat()),
    )
    conn.commit()
    created = get_household(conn, household_id)
    assert created is not None
    return created


def set_phase(conn: sqlite3.Connection, household_id: int, phase: Phase) -> None:
    conn.execute("UPDATE household SET phase = ? WHERE id = ?", (phase.value, household_id))
    conn.commit()


def set_meals(conn: sqlite3.Connection, household_id: int, meals: list[Meal]) -> None:
    ordered = [meal.value for meal in Meal if meal in meals]
    conn.execute(
        "UPDATE household SET meals_json = ? WHERE id = ?", (json.dumps(ordered), household_id)
    )
    conn.commit()


def set_cuisine_prefs(conn: sqlite3.Connection, household_id: int, cuisines: list[str]) -> None:
    conn.execute(
        "UPDATE household SET cuisine_prefs_json = ? WHERE id = ?",
        (json.dumps(cuisines), household_id),
    )
    conn.commit()


def set_profile_confirmed(conn: sqlite3.Connection, household_id: int, confirmed: bool) -> None:
    conn.execute(
        "UPDATE household SET profile_confirmed = ? WHERE id = ?", (int(confirmed), household_id)
    )
    conn.commit()
