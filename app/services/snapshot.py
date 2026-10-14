"""Assembles the read model that the UI renders after every turn."""

import sqlite3

from app import clock
from app.config import Settings
from app.models import StateSnapshot
from app.store import constraints, cook, households, members, pantry


def build_snapshot(
    conn: sqlite3.Connection, household_id: int, settings: Settings
) -> StateSnapshot:
    household = households.ensure_household(conn, household_id)
    return StateSnapshot(
        household=household,
        phase=household.phase,
        members=members.list_members(conn, household_id),
        constraints=constraints.list_active_constraints(conn, household_id),
        cook=cook.get_cook_profile(conn, household_id),
        pantry=pantry.list_pantry(conn, household_id),
        plan=None,
        groceries=[],
        instamart_mode=settings.instamart_mode,
        clock=clock.now(conn, household_id),
    )
