"""SQLite connection and schema. One household per database file."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app import config

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path: Path | str = config.DB_PATH) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """A short-lived connection: `with db() as conn: ...`"""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init() -> None:
    """Create tables and the single household row if they don't exist yet."""
    from app import clock  # avoid an import cycle (clock reads the db)

    with db() as conn:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT OR IGNORE INTO household (id, created_at) VALUES (1, ?)",
            (clock.real_now().isoformat(),),
        )
        conn.commit()


def reset() -> None:
    """Start a fresh household. Telegram links are kept, so people don't have to reconnect."""
    contacts = []
    if config.DB_PATH.exists():
        with db() as conn:
            try:
                contacts = conn.execute("SELECT phone, chat_id, name, linked_at FROM telegram_contact").fetchall()
            except sqlite3.OperationalError:  # older database without the table
                pass
    config.DB_PATH.unlink(missing_ok=True)
    init()
    with db() as conn:
        conn.executemany("INSERT INTO telegram_contact (phone, chat_id, name, linked_at) VALUES (?, ?, ?, ?)", contacts)
        conn.commit()
