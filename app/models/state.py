"""Read model served by `GET /api/state` to drive the UI panels."""

import datetime as dt

from pydantic import Field

from app.config import InstamartMode
from app.models.base import Model
from app.models.enums import Phase
from app.models.household import Constraint, CookProfile, Household, Member, PantryItem
from app.models.plan import GroceryItem, Plan


class StateSnapshot(Model):
    household: Household
    phase: Phase
    members: list[Member]
    constraints: list[Constraint] = Field(description="Active constraints only.")
    cook: CookProfile | None
    pantry: list[PantryItem]
    plan: Plan | None
    groceries: list[GroceryItem]
    instamart_mode: InstamartMode
    clock: dt.datetime
