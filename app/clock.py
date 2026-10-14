"""Simulated clock, persisted per household so demos and evals can jump between cook visits."""

import datetime as dt
import sqlite3
from zoneinfo import ZoneInfo

from app.config import get_settings


def timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def real_now() -> dt.datetime:
    return dt.datetime.now(timezone()).replace(second=0, microsecond=0)


def now(conn: sqlite3.Connection, household_id: int) -> dt.datetime:
    """Simulated current time; initialised to the real time on first read."""
    row = conn.execute(
        "SELECT now FROM sim_clock WHERE household_id = ?", (household_id,)
    ).fetchone()
    if row is not None:
        return dt.datetime.fromisoformat(row["now"])
    current = real_now()
    set_now(conn, household_id, current)
    return current


def set_now(conn: sqlite3.Connection, household_id: int, value: dt.datetime) -> None:
    if value.tzinfo is None:
        raise ValueError("simulated time must be timezone-aware")
    conn.execute(
        "INSERT INTO sim_clock (household_id, now) VALUES (?, ?) "
        "ON CONFLICT (household_id) DO UPDATE SET now = excluded.now",
        (household_id, value.astimezone(timezone()).isoformat()),
    )
    conn.commit()
