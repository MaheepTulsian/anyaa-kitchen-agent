import datetime as dt

import pytest
from pydantic import ValidationError

from app.models import (
    AgeGroup,
    Constraint,
    ConstraintKind,
    CookProfile,
    CookVisit,
    Meal,
    Member,
    SlotPlan,
    Strength,
    slot_key,
)


def test_allergen_is_forced_hard_even_when_user_says_mild() -> None:
    constraint = Constraint(
        kind=ConstraintKind.ALLERGEN,
        value="peanut",
        strength=Strength.SOFT,
        quote="she has a mild peanut allergy",
    )
    assert constraint.strength is Strength.HARD


def test_constraint_requires_quote() -> None:
    with pytest.raises(ValidationError):
        Constraint(
            kind=ConstraintKind.FAVOURITE, value="rajma_chawal", strength=Strength.SOFT, quote=""
        )


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Member.model_validate({"name": "Riya", "age_group": "child", "favourite_colour": "blue"})


def test_spice_level_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Member(name="Rohit", age_group=AgeGroup.ADULT, spice_level=9)


def test_cook_profile_needs_a_visit_unless_family_cooks() -> None:
    with pytest.raises(ValidationError):
        CookProfile(name="Sunita didi")
    assert CookProfile(household_cooks=True).visits == []
    visit = CookVisit(label="morning", start=dt.time(7, 30), minutes=90, meals=[Meal.LUNCH])
    assert CookProfile(visits=[visit]).visits[0].minutes == 90


def test_slot_rejects_empty_servings() -> None:
    with pytest.raises(ValidationError):
        SlotPlan(
            date=dt.date(2026, 10, 16),
            meal=Meal.LUNCH,
            visit="morning",
            dish_id="rajma_chawal",
            servings={AgeGroup.ADULT: 0},
            why="Comfort food for a cold day.",
        )


def test_slot_key_format() -> None:
    assert slot_key(dt.date(2026, 10, 16), Meal.DINNER) == "2026-10-16/dinner"
