"""The cook's schedule, language and repertoire (one cook per household)."""

import json
import sqlite3

from app.models import CookProfile


def get_cook_profile(conn: sqlite3.Connection, household_id: int) -> CookProfile | None:
    row = conn.execute(
        "SELECT * FROM cook_profile WHERE household_id = ?", (household_id,)
    ).fetchone()
    if row is None:
        return None
    return CookProfile.model_validate(
        {
            "name": row["name"],
            "language": row["language"],
            "visits": json.loads(row["visits_json"]),
            "days_off": json.loads(row["days_off_json"]),
            "known_dishes": json.loads(row["known_dishes_json"]),
            "household_cooks": bool(row["household_cooks"]),
            "notes": row["notes"],
        }
    )


def set_cook_profile(conn: sqlite3.Connection, household_id: int, profile: CookProfile) -> None:
    dumped = profile.model_dump(mode="json")
    conn.execute(
        "INSERT INTO cook_profile (household_id, name, language, visits_json, days_off_json, "
        "known_dishes_json, household_cooks, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (household_id) DO UPDATE SET name = excluded.name, "
        "language = excluded.language, visits_json = excluded.visits_json, "
        "days_off_json = excluded.days_off_json, known_dishes_json = excluded.known_dishes_json, "
        "household_cooks = excluded.household_cooks, notes = excluded.notes",
        (
            household_id,
            profile.name,
            profile.language.value,
            json.dumps(dumped["visits"]),
            json.dumps(dumped["days_off"]),
            json.dumps(dumped["known_dishes"]),
            int(profile.household_cooks),
            profile.notes,
        ),
    )
    conn.commit()
