"""Simulated clock, stored in the DB so demos and evals can jump between cook visits."""

import datetime as dt
import sqlite3
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def real_now() -> dt.datetime:
    return dt.datetime.now(IST).replace(second=0, microsecond=0)


def now(conn: sqlite3.Connection, household_id: int) -> dt.datetime:
    """Simulated current time; starts at the real time on first read."""
    row = conn.execute(
        "SELECT now FROM sim_clock WHERE household_id = ?", (household_id,)
    ).fetchone()
    if row:
        return dt.datetime.fromisoformat(row["now"])
    current = real_now()
    set_now(conn, household_id, current)
    return current


def set_now(conn: sqlite3.Connection, household_id: int, value: dt.datetime) -> None:
    conn.execute(
        "INSERT INTO sim_clock (household_id, now) VALUES (?, ?) "
        "ON CONFLICT (household_id) DO UPDATE SET now = excluded.now",
        (household_id, value.astimezone(IST).isoformat()),
    )
    conn.commit()
