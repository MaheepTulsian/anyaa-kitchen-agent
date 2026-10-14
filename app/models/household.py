"""Who lives in the household, what they can eat, and who cooks."""

import datetime as dt
from typing import Self

from pydantic import Field, model_validator

from app.models.base import ItemId, Model, NonEmptyStr
from app.models.enums import (
    AgeGroup,
    ConstraintKind,
    Diet,
    Language,
    Meal,
    Phase,
    Strength,
    Unit,
    Weekday,
)


class Household(Model):
    id: int
    name: str | None = None
    phase: Phase = Phase.ONBOARDING
    meals: list[Meal] = Field(default_factory=lambda: [Meal.LUNCH, Meal.DINNER])
    cuisine_prefs: list[str] = Field(default_factory=list)
    profile_confirmed: bool = False
    created_at: dt.datetime


class Member(Model):
    id: int | None = None
    name: NonEmptyStr
    relation: str | None = None
    age_group: AgeGroup
    diet: Diet = Diet.VEG
    spice_level: int = Field(default=2, ge=0, le=4)
    active: bool = True


class Constraint(Model):
    id: int | None = None
    member_id: int | None = None
    """None means the rule applies to the whole household."""
    kind: ConstraintKind
    value: NonEmptyStr
    strength: Strength
    scope: str | None = None
    """Allergen: `trace` | `ingredient`. Day rules: a weekday such as `tue`."""
    condition: str | None = None
    quote: NonEmptyStr
    """The user's exact words; shown in read-backs and used by evals."""
    valid_from: dt.date | None = None
    superseded_by: int | None = None
    created_at: dt.datetime | None = None

    @model_validator(mode="after")
    def _allergens_are_always_hard(self) -> Self:
        if self.kind is ConstraintKind.ALLERGEN:
            self.strength = Strength.HARD
        return self

    @property
    def is_active(self) -> bool:
        return self.superseded_by is None


class CookVisit(Model):
    label: NonEmptyStr
    start: dt.time
    minutes: int = Field(gt=0, le=480)
    meals: list[Meal] = Field(min_length=1)


class CookProfile(Model):
    name: str | None = None
    language: Language = Language.HINDI
    visits: list[CookVisit] = Field(default_factory=list)
    days_off: list[Weekday] = Field(default_factory=list)
    known_dishes: list[ItemId] = Field(default_factory=list)
    household_cooks: bool = False
    """True when there is no hired cook and the family cooks for itself."""
    notes: str | None = None

    @model_validator(mode="after")
    def _needs_visits_or_household_cook(self) -> Self:
        if not self.visits and not self.household_cooks:
            raise ValueError("a cook profile needs at least one visit, or household_cooks=True")
        return self


class PantryItem(Model):
    item: ItemId
    qty: float = Field(ge=0)
    unit: Unit


class Attendance(Model):
    """An exception to the default of everyone eating every meal."""

    date: dt.date
    meal: Meal
    member_id: int | None = None
    present: bool = True
    guests: int = Field(default=0, ge=0)
    note: str | None = None
