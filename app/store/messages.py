"""Conversation history for both agents, plus the rolling summary of older turns."""

import sqlite3

from app import clock
from app.models import Agent, Message, Role


def append_message(
    conn: sqlite3.Connection, household_id: int, agent: Agent, role: Role, content: str
) -> Message:
    created_at = clock.now(conn, household_id)
    cursor = conn.execute(
        "INSERT INTO message (household_id, agent, role, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (household_id, agent.value, role.value, content, created_at.isoformat()),
    )
    conn.commit()
    return Message(
        id=cursor.lastrowid, agent=agent, role=role, content=content, created_at=created_at
    )


def recent_messages(
    conn: sqlite3.Connection, household_id: int, agent: Agent, limit: int
) -> list[Message]:
    """The latest `limit` messages for one agent, oldest first."""
    rows = conn.execute(
        "SELECT id, agent, role, content, created_at FROM message "
        "WHERE household_id = ? AND agent = ? ORDER BY id DESC LIMIT ?",
        (household_id, agent.value, limit),
    ).fetchall()
    return [Message.model_validate(dict(row)) for row in reversed(rows)]


def get_summary(conn: sqlite3.Connection, household_id: int, agent: Agent) -> str | None:
    row = conn.execute(
        "SELECT content FROM summary WHERE household_id = ? AND agent = ?",
        (household_id, agent.value),
    ).fetchone()
    return str(row["content"]) if row else None


def set_summary(conn: sqlite3.Connection, household_id: int, agent: Agent, content: str) -> None:
    conn.execute(
        "INSERT INTO summary (household_id, agent, content) VALUES (?, ?, ?) "
        "ON CONFLICT (household_id, agent) DO UPDATE SET content = excluded.content",
        (household_id, agent.value, content),
    )
    conn.commit()
