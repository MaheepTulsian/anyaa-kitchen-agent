"""Constraints with supersede-not-delete semantics: the validator only ever reads active rows."""

import sqlite3

from app import clock
from app.models import Constraint, Model

_COLUMNS = (
    "id, member_id, kind, value, strength, scope, condition, quote, valid_from, "
    "superseded_by, created_at"
)


class AddConstraintResult(Model):
    constraint: Constraint
    superseded_id: int | None = None


def _to_model(row: sqlite3.Row) -> Constraint:
    return Constraint.model_validate(dict(row))


def _find_active_same_family(
    conn: sqlite3.Connection, household_id: int, constraint: Constraint
) -> int | None:
    """An earlier active rule about the same (member, kind, value) is replaced by the new one."""
    row = conn.execute(
        "SELECT id FROM constraint_ WHERE household_id = ? AND member_id IS ? AND kind = ? "
        "AND value = ? COLLATE NOCASE AND superseded_by IS NULL ORDER BY id DESC LIMIT 1",
        (household_id, constraint.member_id, constraint.kind.value, constraint.value),
    ).fetchone()
    return int(row["id"]) if row else None


def add_constraint(
    conn: sqlite3.Connection, household_id: int, constraint: Constraint
) -> AddConstraintResult:
    previous_id = _find_active_same_family(conn, household_id, constraint)
    cursor = conn.execute(
        "INSERT INTO constraint_ (household_id, member_id, kind, value, strength, scope, "
        "condition, quote, valid_from, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            household_id,
            constraint.member_id,
            constraint.kind.value,
            constraint.value,
            constraint.strength.value,
            constraint.scope,
            constraint.condition,
            constraint.quote,
            constraint.valid_from.isoformat() if constraint.valid_from else None,
            clock.now(conn, household_id).isoformat(),
        ),
    )
    new_id = cursor.lastrowid
    if previous_id is not None:
        conn.execute("UPDATE constraint_ SET superseded_by = ? WHERE id = ?", (new_id, previous_id))
    conn.commit()
    row = conn.execute(f"SELECT {_COLUMNS} FROM constraint_ WHERE id = ?", (new_id,)).fetchone()
    return AddConstraintResult(constraint=_to_model(row), superseded_id=previous_id)


def list_active_constraints(conn: sqlite3.Connection, household_id: int) -> list[Constraint]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM constraint_ WHERE household_id = ? AND superseded_by IS NULL "
        "ORDER BY id",
        (household_id,),
    ).fetchall()
    return [_to_model(row) for row in rows]


def list_constraints_for_member(
    conn: sqlite3.Connection, household_id: int, member_id: int
) -> list[Constraint]:
    return [c for c in list_active_constraints(conn, household_id) if c.member_id == member_id]
