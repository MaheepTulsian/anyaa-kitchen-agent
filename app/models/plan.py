"""Meal plans: what the planner proposes, what the validator reports, what gets stored."""

import datetime as dt
from typing import Self

from pydantic import Field, model_validator

from app.models.base import ItemId, Model, NonEmptyStr
from app.models.enums import (
    AgeGroup,
    Channel,
    Meal,
    PlanStatus,
    PrepOwner,
    Severity,
    Unit,
    VariationChange,
)

Servings = dict[AgeGroup, int]
"""Head-count per age group for one slot; guests are counted as adults."""


def slot_key(date: dt.date, meal: Meal) -> str:
    """Stable slot identifier used in violations, tools and logs, e.g. `2026-10-16/lunch`."""
    return f"{date.isoformat()}/{meal.value}"


class Variation(Model):
    member: NonEmptyStr
    """Member name or group as the household says it, e.g. `Dadi`, `kids`."""
    change: VariationChange
    at: str | None = None
    """Variation point from the dish, e.g. `before_tadka`."""
    detail: str | None = None
    """Free-text specifics, e.g. `brown rice instead of white`, `omit peanuts`."""
    ingredient: ItemId | None = None
    """Ingredient omitted (`omit_ingredient`) or the replacement side/dish id."""


class PrepTask(Model):
    task: NonEmptyStr
    by: dt.datetime
    owner: PrepOwner
    visit_ref: str | None = None


class SlotPlan(Model):
    date: dt.date
    meal: Meal
    visit: NonEmptyStr
    dish_id: ItemId
    side_dish_ids: list[ItemId] = Field(default_factory=list)
    servings: Servings
    variations: list[Variation] = Field(default_factory=list)
    prep_tasks: list[PrepTask] = Field(default_factory=list)
    why: NonEmptyStr

    @property
    def key(self) -> str:
        return slot_key(self.date, self.meal)

    @model_validator(mode="after")
    def _servings_are_positive(self) -> Self:
        if any(count < 0 for count in self.servings.values()):
            raise ValueError("servings cannot be negative")
        if sum(self.servings.values()) == 0:
            raise ValueError("a planned slot must serve at least one person")
        return self


class PlanProposal(Model):
    slots: list[SlotPlan]
    new_dishes: list[dict[str, object]] = Field(default_factory=list)
    """Off-catalog dishes in catalog shape; always treated as unverified."""
    notes_for_household: list[str] = Field(default_factory=list)


class Violation(Model):
    rule: NonEmptyStr
    severity: Severity
    slot: str | None = None
    member: str | None = None
    detail: NonEmptyStr
    repair_hint: NonEmptyStr


class StoredSlot(SlotPlan):
    """A slot as persisted, with bookkeeping the planner never sets."""

    id: int
    locked: bool = False
    stale: bool = False
    attendee_ids: list[int] = Field(default_factory=list)


class Plan(Model):
    id: int
    version: int = Field(ge=1)
    status: PlanStatus
    window_start: dt.date
    window_end: dt.date
    created_at: dt.datetime
    slots: list[StoredSlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def _window_is_ordered(self) -> Self:
        if self.window_end < self.window_start:
            raise ValueError("window_end is before window_start")
        return self


class GroceryItem(Model):
    item: ItemId
    qty: float = Field(gt=0)
    unit: Unit
    pack_qty: float | None = Field(default=None, gt=0)
    pack_unit: Unit | None = None
    packs: int | None = Field(default=None, ge=1)
    channel: Channel
    needed_by: dt.datetime
    sku: dict[str, object] | None = None
