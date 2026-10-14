import datetime as dt
import sqlite3

import pytest

from app import clock
from app.models import (
    AgeGroup,
    Agent,
    Constraint,
    ConstraintKind,
    CookProfile,
    CookVisit,
    Diet,
    Meal,
    Member,
    PantryItem,
    Phase,
    Role,
    Strength,
    Unit,
    Weekday,
)
from app.store import constraints, cook, households, members, messages, pantry
from tests.conftest import HOUSEHOLD_ID


def _add_riya(conn: sqlite3.Connection) -> Member:
    return members.upsert_member(
        conn, HOUSEHOLD_ID, Member(name="Riya", age_group=AgeGroup.CHILD, spice_level=1)
    )


def test_household_defaults(conn: sqlite3.Connection) -> None:
    household = households.ensure_household(conn, HOUSEHOLD_ID)
    assert household.phase is Phase.ONBOARDING
    assert household.meals == [Meal.LUNCH, Meal.DINNER]
    households.set_meals(conn, HOUSEHOLD_ID, [Meal.DINNER, Meal.BREAKFAST])
    updated = households.get_household(conn, HOUSEHOLD_ID)
    assert updated is not None
    assert updated.meals == [Meal.BREAKFAST, Meal.DINNER]


def test_member_upsert_is_case_insensitive_update(conn: sqlite3.Connection) -> None:
    papa = members.upsert_member(
        conn, HOUSEHOLD_ID, Member(name="Papa", age_group=AgeGroup.ELDERLY, diet=Diet.VEG)
    )
    again = members.upsert_member(
        conn, HOUSEHOLD_ID, Member(name="papa", age_group=AgeGroup.ELDERLY, diet=Diet.EGGETARIAN)
    )
    assert again.id == papa.id
    assert again.name == "Papa"
    assert again.diet is Diet.EGGETARIAN
    assert len(members.list_members(conn, HOUSEHOLD_ID)) == 1


def test_deactivated_member_is_hidden_but_kept(conn: sqlite3.Connection) -> None:
    _add_riya(conn)
    assert members.deactivate_member(conn, HOUSEHOLD_ID, "riya")
    assert members.list_members(conn, HOUSEHOLD_ID) == []
    assert len(members.list_members(conn, HOUSEHOLD_ID, active_only=False)) == 1
    assert not members.deactivate_member(conn, HOUSEHOLD_ID, "Nobody")


def test_new_constraint_supersedes_same_family(conn: sqlite3.Connection) -> None:
    riya = _add_riya(conn)
    first = constraints.add_constraint(
        conn,
        HOUSEHOLD_ID,
        Constraint(
            member_id=riya.id,
            kind=ConstraintKind.ALLERGEN,
            value="peanut",
            strength=Strength.HARD,
            scope="ingredient",
            quote="peanuts se allergy hai",
        ),
    )
    second = constraints.add_constraint(
        conn,
        HOUSEHOLD_ID,
        Constraint(
            member_id=riya.id,
            kind=ConstraintKind.ALLERGEN,
            value="Peanut",
            strength=Strength.HARD,
            scope="trace",
            quote="even peanut oil",
        ),
    )
    assert first.superseded_id is None
    assert second.superseded_id == first.constraint.id
    active = constraints.list_active_constraints(conn, HOUSEHOLD_ID)
    assert [c.scope for c in active] == ["trace"]


def test_different_members_do_not_supersede(conn: sqlite3.Connection) -> None:
    riya = _add_riya(conn)
    household_rule = Constraint(
        kind=ConstraintKind.DIET_DAY,
        value="veg",
        strength=Strength.HARD,
        scope="tue",
        quote="Tuesday ko sab veg",
    )
    member_rule = household_rule.model_copy(update={"member_id": riya.id})
    constraints.add_constraint(conn, HOUSEHOLD_ID, household_rule)
    result = constraints.add_constraint(conn, HOUSEHOLD_ID, member_rule)
    assert result.superseded_id is None
    assert len(constraints.list_active_constraints(conn, HOUSEHOLD_ID)) == 2


def test_cook_profile_round_trip(conn: sqlite3.Connection) -> None:
    profile = CookProfile(
        name="Sunita didi",
        visits=[
            CookVisit(
                label="morning",
                start=dt.time(7, 30),
                minutes=90,
                meals=[Meal.BREAKFAST, Meal.LUNCH],
            ),
            CookVisit(label="evening", start=dt.time(18, 30), minutes=60, meals=[Meal.DINNER]),
        ],
        days_off=[Weekday.SUN],
        known_dishes=["dal_tadka", "rajma_chawal"],
    )
    cook.set_cook_profile(conn, HOUSEHOLD_ID, profile)
    assert cook.get_cook_profile(conn, HOUSEHOLD_ID) == profile


def test_pantry_zero_removes_item(conn: sqlite3.Connection) -> None:
    pantry.set_pantry_item(conn, HOUSEHOLD_ID, PantryItem(item="rice", qty=5000, unit=Unit.GRAM))
    assert pantry.list_pantry(conn, HOUSEHOLD_ID)[0].qty == 5000
    pantry.set_pantry_item(conn, HOUSEHOLD_ID, PantryItem(item="rice", qty=0, unit=Unit.GRAM))
    assert pantry.list_pantry(conn, HOUSEHOLD_ID) == []


def test_recent_messages_are_oldest_first_per_agent(conn: sqlite3.Connection) -> None:
    for text in ("one", "two", "three"):
        messages.append_message(conn, HOUSEHOLD_ID, Agent.HOUSEHOLD, Role.USER, text)
    messages.append_message(conn, HOUSEHOLD_ID, Agent.COOK, Role.USER, "cook note")
    recent = messages.recent_messages(conn, HOUSEHOLD_ID, Agent.HOUSEHOLD, limit=2)
    assert [m.content for m in recent] == ["two", "three"]


def test_simulated_clock_persists_and_requires_timezone(conn: sqlite3.Connection) -> None:
    target = dt.datetime(2026, 10, 16, 7, 30, tzinfo=clock.timezone())
    clock.set_now(conn, HOUSEHOLD_ID, target)
    assert clock.now(conn, HOUSEHOLD_ID) == target
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.set_now(conn, HOUSEHOLD_ID, dt.datetime(2026, 10, 16, 7, 30))
