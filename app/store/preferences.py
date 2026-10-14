"""Free-form household preferences: what each person needs, avoids and loves."""

import sqlite3

from app import clock
from app.models import Preference

_COLUMNS = "id, member, category, detail, strict, quote, created_at"


def _to_model(row: sqlite3.Row) -> Preference:
    return Preference.model_validate({**dict(row), "strict": bool(row["strict"])})


def add_preference(conn: sqlite3.Connection, household_id: int, pref: Preference) -> Preference:
    cursor = conn.execute(
        "INSERT INTO preference (household_id, member, category, detail, strict, quote, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            household_id,
            pref.member,
            pref.category.lower(),
            pref.detail,
            int(pref.strict),
            pref.quote,
            clock.now(conn, household_id).isoformat(),
        ),
    )
    conn.commit()
    return pref.model_copy(update={"id": cursor.lastrowid})


def remove_preference(conn: sqlite3.Connection, household_id: int, pref_id: int) -> bool:
    cursor = conn.execute(
        "DELETE FROM preference WHERE household_id = ? AND id = ?", (household_id, pref_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def list_preferences(conn: sqlite3.Connection, household_id: int) -> list[Preference]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM preference WHERE household_id = ? ORDER BY id", (household_id,)
    ).fetchall()
    return [_to_model(row) for row in rows]
