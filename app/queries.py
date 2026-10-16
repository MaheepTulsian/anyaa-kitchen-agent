"""Every database read and write, in one place. Each function takes an open connection."""

import json
import sqlite3

from app import clock
from app.models import Agent, CookProfile, Escalation, Household, Meal, Member, Message, PantryItem, Phase, Preference, Role, StoredPlan

# --- household --------------------------------------------------------------------------------


def get_household(conn: sqlite3.Connection) -> Household:
    row = conn.execute("SELECT * FROM household WHERE id = 1").fetchone()
    return Household(
        id=row["id"],
        phase=row["phase"],
        meals=json.loads(row["meals_json"]),
        meals_set=bool(row["meals_set"]),
        profile_confirmed=bool(row["profile_confirmed"]),
        created_at=row["created_at"],
    )


def set_phase(conn: sqlite3.Connection, phase: Phase) -> None:
    conn.execute("UPDATE household SET phase = ? WHERE id = 1", (phase.value,))
    conn.commit()


def set_meals(conn: sqlite3.Connection, meals: list[Meal]) -> None:
    """Which meals Anyaa plans, kept in breakfast-lunch-dinner order."""
    ordered = [meal.value for meal in Meal if meal in meals]
    conn.execute("UPDATE household SET meals_json = ?, meals_set = 1 WHERE id = 1", (json.dumps(ordered),))
    conn.commit()


def confirm_profile(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE household SET profile_confirmed = 1 WHERE id = 1")
    conn.commit()


# --- members ----------------------------------------------------------------------------------


def _member(row: sqlite3.Row) -> Member:
    return Member.model_validate({**dict(row), "active": bool(row["active"]), "diet_confirmed": bool(row["diet_confirmed"])})


def get_member(conn: sqlite3.Connection, name: str) -> Member | None:
    """Look a member up by the name the family uses (case-insensitive)."""
    row = conn.execute("SELECT * FROM member WHERE name = ?", (name.strip(),)).fetchone()
    return _member(row) if row else None


def list_members(conn: sqlite3.Connection) -> list[Member]:
    return [_member(r) for r in conn.execute("SELECT * FROM member WHERE active = 1 ORDER BY id")]


def save_member(conn: sqlite3.Connection, member: Member) -> Member:
    """Add a member, or update the one with the same name."""
    conn.execute(
        "INSERT INTO member (name, relation, age_group, diet, spice_level, diet_confirmed, active) "
        "VALUES (?, ?, ?, ?, ?, ?, 1) "
        "ON CONFLICT (name) DO UPDATE SET relation = excluded.relation, age_group = excluded.age_group, "
        "diet = excluded.diet, spice_level = excluded.spice_level, diet_confirmed = excluded.diet_confirmed, active = 1",
        (member.name, member.relation, member.age_group.value, member.diet.value, member.spice_level, int(member.diet_confirmed)),
    )
    conn.commit()
    return get_member(conn, member.name)  # type: ignore[return-value]


def rename_member(conn: sqlite3.Connection, old: str, new: str) -> bool:
    """Give someone their real name ("Friend" → "Sushil"); their notes follow them."""
    cursor = conn.execute("UPDATE member SET name = ? WHERE name = ?", (new.strip(), old.strip()))
    conn.execute("UPDATE preference SET member = ? WHERE member = ? COLLATE NOCASE", (new.strip(), old.strip()))
    conn.commit()
    return cursor.rowcount > 0


def remove_member(conn: sqlite3.Connection, name: str) -> bool:
    """Soft-remove, so older notes about them still make sense. False if not found."""
    cursor = conn.execute("UPDATE member SET active = 0 WHERE name = ?", (name.strip(),))
    conn.commit()
    return cursor.rowcount > 0


# --- preferences ------------------------------------------------------------------------------


def list_preferences(conn: sqlite3.Connection) -> list[Preference]:
    rows = conn.execute("SELECT * FROM preference ORDER BY id")
    return [Preference.model_validate({**dict(r), "strict": bool(r["strict"])}) for r in rows]


def add_preference(conn: sqlite3.Connection, pref: Preference) -> Preference:
    cursor = conn.execute(
        "INSERT INTO preference (member, category, detail, strict, quote, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (pref.member, pref.category.lower(), pref.detail, int(pref.strict), pref.quote, clock.now(conn).isoformat()),
    )
    conn.commit()
    return pref.model_copy(update={"id": cursor.lastrowid})


def remove_preference(conn: sqlite3.Connection, pref_id: int) -> bool:
    cursor = conn.execute("DELETE FROM preference WHERE id = ?", (pref_id,))
    conn.commit()
    return cursor.rowcount > 0


# --- cook and pantry --------------------------------------------------------------------------


def get_cook(conn: sqlite3.Connection) -> CookProfile | None:
    row = conn.execute("SELECT profile_json FROM cook WHERE id = 1").fetchone()
    return CookProfile.model_validate_json(row["profile_json"]) if row else None


def save_cook(conn: sqlite3.Connection, profile: CookProfile) -> None:
    conn.execute(
        "INSERT INTO cook (id, profile_json) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET profile_json = excluded.profile_json",
        (profile.model_dump_json(),),
    )
    conn.commit()


def list_pantry(conn: sqlite3.Connection) -> list[PantryItem]:
    return [PantryItem.model_validate(dict(r)) for r in conn.execute("SELECT * FROM pantry ORDER BY item")]


def set_pantry_item(conn: sqlite3.Connection, item: PantryItem) -> None:
    """Set what's on hand; a quantity of zero removes the item."""
    if item.qty == 0:
        conn.execute("DELETE FROM pantry WHERE item = ?", (item.item,))
    else:
        conn.execute(
            "INSERT INTO pantry (item, qty, unit) VALUES (?, ?, ?) "
            "ON CONFLICT (item) DO UPDATE SET qty = excluded.qty, unit = excluded.unit",
            (item.item, item.qty, item.unit.value),
        )
    conn.commit()


# --- plan -------------------------------------------------------------------------------------


def get_plan(conn: sqlite3.Connection) -> StoredPlan | None:
    row = conn.execute("SELECT plan_json FROM plan WHERE id = 1").fetchone()
    return StoredPlan.model_validate_json(row["plan_json"]) if row else None


def save_plan(conn: sqlite3.Connection, stored: StoredPlan) -> None:
    conn.execute(
        "INSERT INTO plan (id, plan_json) VALUES (1, ?) ON CONFLICT (id) DO UPDATE SET plan_json = excluded.plan_json",
        (stored.model_dump_json(),),
    )
    conn.commit()


# --- conversation -----------------------------------------------------------------------------


def add_message(conn: sqlite3.Connection, agent: Agent, role: Role, content: str) -> Message:
    created_at = clock.now(conn)
    cursor = conn.execute(
        "INSERT INTO message (agent, role, content, created_at) VALUES (?, ?, ?, ?)",
        (agent.value, role.value, content, created_at.isoformat()),
    )
    conn.commit()
    return Message(id=cursor.lastrowid, agent=agent, role=role, content=content, created_at=created_at)


def list_messages(conn: sqlite3.Connection, agent: Agent) -> list[Message]:
    rows = conn.execute("SELECT * FROM message WHERE agent = ? ORDER BY id", (agent.value,))
    return [Message.model_validate(dict(r)) for r in rows]


def get_session(conn: sqlite3.Connection, agent: Agent, node: str) -> str | None:
    """The SDK session that holds this node's conversation, if it has started."""
    row = conn.execute("SELECT session_id FROM agent_session WHERE agent = ? AND node = ?", (agent.value, node)).fetchone()
    return row["session_id"] if row else None


def save_session(conn: sqlite3.Connection, agent: Agent, node: str, session_id: str) -> None:
    conn.execute(
        "INSERT INTO agent_session (agent, node, session_id) VALUES (?, ?, ?) "
        "ON CONFLICT (agent, node) DO UPDATE SET session_id = excluded.session_id",
        (agent.value, node, session_id),
    )
    conn.commit()


# --- cook side --------------------------------------------------------------------------------


def add_escalation(conn: sqlite3.Connection, esc: Escalation) -> Escalation:
    cursor = conn.execute(
        "INSERT INTO escalation (question, option_a, option_b, status, created_at) VALUES (?, ?, ?, 'open', ?)",
        (esc.question, esc.option_a, esc.option_b, clock.now(conn).isoformat()),
    )
    conn.commit()
    return esc.model_copy(update={"id": cursor.lastrowid})


def open_escalations(conn: sqlite3.Connection) -> list[Escalation]:
    rows = conn.execute("SELECT * FROM escalation WHERE status = 'open' ORDER BY id")
    return [Escalation.model_validate(dict(r)) for r in rows]


def resolve_escalation(conn: sqlite3.Connection, esc_id: int, choice: str) -> None:
    conn.execute("UPDATE escalation SET status = ? WHERE id = ?", (choice, esc_id))
    conn.commit()


def mark_sent(conn: sqlite3.Connection, key: str) -> bool:
    """Record a cook message as sent. False if it was already sent (so it's never sent twice)."""
    cursor = conn.execute("INSERT OR IGNORE INTO sent (key, at) VALUES (?, ?)", (key, clock.now(conn).isoformat()))
    conn.commit()
    return cursor.rowcount > 0


def was_sent(conn: sqlite3.Connection, key: str) -> bool:
    return conn.execute("SELECT 1 FROM sent WHERE key = ?", (key,)).fetchone() is not None
