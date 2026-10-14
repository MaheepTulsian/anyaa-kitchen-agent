"""Read model served by `GET /api/state` to drive the UI panels."""

import datetime as dt

from app.models.base import Model
from app.models.enums import Phase
from app.models.household import CookProfile, Household, Member, PantryItem, Preference
from app.models.plan import GroceryItem, Plan


class StateSnapshot(Model):
    household: Household
    phase: Phase
    members: list[Member]
    preferences: list[Preference]
    cook: CookProfile | None
    pantry: list[PantryItem]
    plan: Plan | None
    groceries: list[GroceryItem]
    instamart_mode: str
    clock: dt.datetime
