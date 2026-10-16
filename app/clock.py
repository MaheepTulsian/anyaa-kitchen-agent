"""Simulated clock: real time plus an offset, so demos and evals can jump ahead to the next cook visit.

The offset is stored in the database. With no offset, it's simply the real time in India.
"""

import datetime as dt
import json
import sqlite3
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def real_now() -> dt.datetime:
    return dt.datetime.now(IST).replace(second=0, microsecond=0)


def _offset(conn: sqlite3.Connection) -> dt.timedelta:
    row = conn.execute("SELECT now FROM clock WHERE id = 1").fetchone()
    if row and row["now"].startswith("{"):
        return dt.timedelta(minutes=json.loads(row["now"])["offset_minutes"])
    return dt.timedelta(0)  # no offset yet (or an old fixed-time value): real time


def now(conn: sqlite3.Connection) -> dt.datetime:
    return real_now() + _offset(conn)


def set_now(conn: sqlite3.Connection, value: dt.datetime) -> None:
    """Make the simulated time `value` from now on (it keeps moving forward with real time)."""
    minutes = round((value.astimezone(IST) - real_now()).total_seconds() / 60)
    conn.execute(
        "INSERT INTO clock (id, now) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET now = excluded.now",
        (json.dumps({"offset_minutes": minutes}),),
    )
    conn.commit()
