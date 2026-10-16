"""Every data shape in the app, as Pydantic models.

These are the boundaries: what tools accept from the LLM, what the DB returns, what the API
sends to the browser. Unknown fields are rejected everywhere, so LLM drift fails loudly instead
of being silently stored.
"""

import datetime as dt
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)]


# --- vocabularies -----------------------------------------------------------------------------


class Phase(StrEnum):
    """The household agent's current node, in order (see flow.py)."""

    FAMILY = "FAMILY"  # who eats at home and their diets
    FOOD_NEEDS = "FOOD_NEEDS"  # allergies, intolerances, health, never-eat, fasting
    TASTES = "TASTES"  # what they love, everyday food, spice
    KITCHEN = "KITCHEN"  # the cook and which meals to plan
    CONFIRM = "CONFIRM"  # summary of what was noted, then confirm
    MEAL_PLAN = "MEAL_PLAN"  # agree today and tomorrow, then the whole week
    GROCERIES = "GROCERIES"  # one yes fills the Instamart cart; vegetables go to the sabziwala
    RUNNING = "RUNNING"  # everyday mode: questions, changes, the cook's A/B questions


class Meal(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"


class Weekday(StrEnum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


class AgeGroup(StrEnum):
    TODDLER = "toddler"
    CHILD = "child"
    TEEN = "teen"
    ADULT = "adult"
    ELDERLY = "elderly"


class Diet(StrEnum):
    VEG = "veg"
    EGGETARIAN = "eggetarian"
    NONVEG = "nonveg"
    JAIN = "jain"
    VEGAN = "vegan"


class Unit(StrEnum):
    GRAM = "g"
    MILLILITRE = "ml"
    PIECE = "pc"


class Agent(StrEnum):
    HOUSEHOLD = "household"
    COOK = "cook"


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


# --- the household ----------------------------------------------------------------------------


class Household(Model):
    id: int
    phase: Phase = Phase.FAMILY
    meals: list[Meal] = Field(default_factory=lambda: [Meal.LUNCH, Meal.DINNER])
    meals_set: bool = False  # the user agreed which meals to plan
    profile_confirmed: bool = False
    created_at: dt.datetime


class Member(Model):
    id: int | None = None
    name: Text  # as the family says it: "Papa", "Sister", "Me"
    relation: str | None = None
    age_group: AgeGroup
    diet: Diet = Diet.VEG
    spice_level: int = Field(default=2, ge=0, le=4)
    diet_confirmed: bool = False  # the user said it, rather than us guessing
    active: bool = True


class Preference(Model):
    """Anything the household tells us about food, as a free-form note the LLM writes and reads."""

    id: int | None = None
    member: str | None = None  # member name, or None for the whole household
    category: Text  # free text: allergy, health, dislike, favourite, fasting, cuisine, ...
    detail: Text  # the fact in plain words: "taro root, makes her itchy; traces are fine"
    strict: bool = False  # must never be broken: allergies, never-eat, religious, fasting
    quote: Text  # the user's exact words
    created_at: dt.datetime | None = None


class CookVisit(Model):
    label: Text  # "morning", "evening"
    start: dt.time
    minutes: int = Field(gt=0, le=480)
    meals: list[Meal] = Field(min_length=1)


class CookProfile(Model):
    name: str | None = None
    phone: str | None = None  # Telegram: briefs and voice notes go here
    visits: list[CookVisit] = Field(default_factory=list)
    days_off: list[Weekday] = Field(default_factory=list)
    known_dishes: list[Name] = Field(default_factory=list)
    household_cooks: bool = False  # no hired cook; the family cooks
    notes: str | None = None

    @model_validator(mode="after")
    def _needs_visits_or_family_cook(self) -> Self:
        if not self.visits and not self.household_cooks:
            raise ValueError("a cook profile needs at least one visit, or household_cooks=True")
        return self


class PantryItem(Model):
    item: Name
    qty: float = Field(ge=0)
    unit: Unit


# --- meal plan --------------------------------------------------------------------------------


class Dish(Model):
    name: Text
    for_whom: list[str]  # member names, or ["everyone"]
    ingredients: list[Text]  # everything that goes in, including oil, tempering and garnish
    cook_note: str | None = None  # a per-person tweak at the exact step: "take out Papa's portion before adding salt"


class PlannedMeal(Model):
    day: dt.date
    meal: Meal
    dishes: list[Dish] = Field(min_length=1)
    why: str  # one short line for the family


class GroceryLine(Model):
    item: Text  # plain name: "toor dal", "onion"
    quantity: Text  # as you'd say it: "1 kg", "500 g", "6"
    where: Literal["instamart", "sabziwala"]  # fresh vegetables, herbs and fruit go to the sabziwala


class MealPlan(Model):
    meals: list[PlannedMeal] = Field(min_length=1)
    prep_ahead: list[str] = []  # "Monday evening: soak 250 g rajma for Tuesday lunch"
    groceries: list[GroceryLine] = []  # what to buy, after what's already in the pantry
    notes_for_family: list[str] = []  # trade-offs worth saying out loud


class SketchDish(Model):
    name: Text
    for_whom: list[str]  # member names, or ["everyone"]


class SketchMeal(Model):
    day: dt.date
    meal: Meal
    dishes: list[SketchDish] = Field(min_length=1)


class MenuSketch(Model):
    """Step 1 of planning: just what's cooked for whom, for every day (small, so it's fast)."""

    meals: list[SketchMeal] = Field(min_length=1)
    prep_ahead: list[str] = []
    notes_for_family: list[str] = []


class DayDetail(Model):
    """Step 2: one day's meals in full, written in parallel for each day."""

    meals: list[PlannedMeal] = Field(min_length=1)


class GroceryList(Model):
    """Step 3: what to buy for the whole plan."""

    groceries: list[GroceryLine] = []


class SafetyIssue(Model):
    day: dt.date
    meal: Meal
    dish: str
    member: str
    problem: str  # "contains groundnut oil; Riya is allergic to peanuts even in traces"


class SafetyReport(Model):
    issues: list[SafetyIssue] = []


class StoredPlan(Model):
    plan: MealPlan
    stage: Literal["near", "week"] = "near"  # near = today and tomorrow; week = the whole week
    status: Literal["draft", "agreed"] = "draft"
    issues: list[SafetyIssue] = []  # left after the planner's fixes; must be empty to approve
    cart: dict[str, Any] | None = None  # filled cart summary, once approved


# --- conversation and logs --------------------------------------------------------------------


class Message(Model):
    id: int | None = None
    agent: Agent
    role: Role
    content: str
    created_at: dt.datetime


class Event(Model):
    """One line in logs/events.jsonl."""

    ts: dt.datetime
    turn_id: str | None = None  # every line of one turn shares this id
    agent: Agent | None = None
    type: str  # turn_start | tool_call | turn_end | phase_change | error
    data: dict[str, Any] = Field(default_factory=dict)
    ms: int | None = None  # milliseconds since the turn started


class Escalation(Model):
    """Something the cook agent couldn't settle safely on its own: the household picks A or B."""

    id: int | None = None
    question: str
    option_a: str
    option_b: str
    status: Literal["open", "a", "b"] = "open"
    created_at: dt.datetime | None = None


class State(Model):
    """What the UI panels show (GET /api/state)."""

    household: Household
    members: list[Member]
    preferences: list[Preference]
    cook: CookProfile | None
    pantry: list[PantryItem]
    plan: StoredPlan | None
    escalations: list[Escalation] = []
    instamart_mode: str
    clock: dt.datetime
