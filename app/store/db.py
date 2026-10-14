"""SQLite connection handling and schema bootstrap."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a connection with row access by column name and foreign keys enforced."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Commit on success, roll back on any error."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
