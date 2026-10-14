"""Household members, keyed by the name the family uses ("Papa", "Dadi", "Riya")."""

import sqlite3

from app.models import Member

_COLUMNS = "id, name, relation, age_group, diet, spice_level, active"


def _to_model(row: sqlite3.Row) -> Member:
    return Member.model_validate({**dict(row), "active": bool(row["active"])})


def get_member_by_name(conn: sqlite3.Connection, household_id: int, name: str) -> Member | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM member WHERE household_id = ? AND name = ? COLLATE NOCASE",
        (household_id, name.strip()),
    ).fetchone()
    return _to_model(row) if row else None


def get_member(conn: sqlite3.Connection, member_id: int) -> Member | None:
    row = conn.execute(f"SELECT {_COLUMNS} FROM member WHERE id = ?", (member_id,)).fetchone()
    return _to_model(row) if row else None


def list_members(
    conn: sqlite3.Connection, household_id: int, *, active_only: bool = True
) -> list[Member]:
    query = f"SELECT {_COLUMNS} FROM member WHERE household_id = ?"
    if active_only:
        query += " AND active = 1"
    rows = conn.execute(query + " ORDER BY id", (household_id,)).fetchall()
    return [_to_model(row) for row in rows]


def upsert_member(conn: sqlite3.Connection, household_id: int, member: Member) -> Member:
    """Insert a new member or update the existing one with the same name (case-insensitive)."""
    existing = get_member_by_name(conn, household_id, member.name)
    values = (
        member.relation,
        member.age_group.value,
        member.diet.value,
        member.spice_level,
        int(member.active),
    )
    if existing is None:
        cursor = conn.execute(
            "INSERT INTO member (household_id, name, relation, age_group, diet, spice_level, "
            "active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (household_id, member.name, *values),
        )
        member_id = cursor.lastrowid
    else:
        conn.execute(
            "UPDATE member SET relation = ?, age_group = ?, diet = ?, spice_level = ?, active = ? "
            "WHERE id = ?",
            (*values, existing.id),
        )
        member_id = existing.id
    conn.commit()
    assert member_id is not None
    stored = get_member(conn, member_id)
    assert stored is not None
    return stored


def deactivate_member(conn: sqlite3.Connection, household_id: int, name: str) -> bool:
    """Soft-remove a member so history and preferences stay traceable. False if not found."""
    cursor = conn.execute(
        "UPDATE member SET active = 0 WHERE household_id = ? AND name = ? COLLATE NOCASE",
        (household_id, name.strip()),
    )
    conn.commit()
    return cursor.rowcount > 0
