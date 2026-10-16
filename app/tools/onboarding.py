"""Onboarding tools, grouped by the node that may use them.

Each node only gets its own list (FAMILY_TOOLS, NEEDS_TOOLS, ...), so the agent can't wander into
another node's topic. Each node ends with a `*_done` tool whose requirements are checked here, in
code; if something is missing it refuses and says what, and the node carries on.
"""

import re

from pydantic import Field

from app import planner, profile, queries, swiggy, telegram
from app.db import db
from app.models import AgeGroup, CookProfile, Diet, Meal, Member, Model, PantryItem, Phase, Preference, Unit, Weekday
from app.tools import ToolError, anyaa_tool

# True once the summary was read out with nothing changed since; any write clears it, so
# confirm_profile always follows a fresh summary.
_summary_current = False


def _changed() -> None:
    global _summary_current
    _summary_current = False


def _advance(phase: Phase) -> dict:
    with db() as conn:
        queries.set_phase(conn, phase)
    return {"done": True, "next": "The next part starts on its own. Don't say anything more this turn."}


# --- inputs -----------------------------------------------------------------------------------


class NoInput(Model):
    pass


class MemberInput(Model):
    name: str = Field(description='What the family calls them: "Mom", "Papa", "Sister", "Me" for the speaker.')
    relation: str | None = Field(None, description="e.g. mother, father, sister, flatmate, son")
    age_group: AgeGroup
    diet: Diet = Field(
        description="nonveg: eats chicken, fish or meat (eggs too). eggetarian: eggs but NO meat. "
        "veg: no meat, no eggs. jain: veg without onion, garlic or root vegetables. vegan: no dairy either."
    )
    diet_confirmed: bool = Field(description="true only if the user said this person's diet; false if you guessed it.")
    diet_words: str | None = Field(None, description="When diet_confirmed is true: the user's exact words about what "
                                   'this person eats, e.g. "I eat egg or chicken sometimes".')
    previous_name: str | None = Field(None, description='Set when you learn the real name of someone saved under '
                                      'another name ("Friend" → "Sushil"), so they are renamed, not added twice.')
    spice_level: int | None = Field(None, ge=0, le=4, description="0 none .. 4 very spicy; omit if unknown")


class RemoveMemberInput(Model):
    name: str


class PreferenceInput(Model):
    member: str | None = Field(None, description="Member name as saved, or null for the whole household.")
    category: str = Field(
        description="Short label: allergy, intolerance, health, avoid, dislike, favourite, fasting, religious, "
        "cuisine, spice, routine."
    )
    detail: str = Field(
        description='The fact in plain words, complete enough to plan a meal from: "peanuts, even traces like '
        'groundnut oil or garnish", "high protein, goes to the gym", "none".'
    )
    strict: bool = Field(
        description="true if it must never be broken: allergies, intolerances, never-eat, religious and fasting rules."
    )
    quote: str = Field(description="The user's exact words.")


class AddPreferencesInput(Model):
    items: list[PreferenceInput] = Field(min_length=1)


class ParkInput(Model):
    member: str | None = Field(None, description="Who it's about, if anyone in particular (a saved name).")
    fact: str = Field(description='What they said, in plain words: "Sushil can\'t have curd, lassi, raita or kadhi".')
    quote: str = Field(description="Their exact words.")


class RemovePreferenceInput(Model):
    id: int = Field(description="The #id shown in the household profile.")


class VisitInput(Model):
    label: str = Field(description='"morning", "evening"')
    start: str = Field(description="24h HH:MM, e.g. 07:30")
    minutes: int = Field(gt=0, le=480)
    meals: list[Meal] = Field(min_length=1)


class CookInput(Model):
    """Only the fields you pass change; everything else stays as saved."""

    name: str | None = None
    phone: str | None = Field(None, description="The cook's mobile number, for Telegram.")
    household_cooks: bool | None = Field(None, description="true if there's no cook and the family cooks.")
    visits: list[VisitInput] | None = None
    days_off: list[Weekday] | None = None
    known_dishes: list[str] | None = None
    notes: str | None = Field(None, description='What they tend to get wrong, e.g. "over-salts sabzi".')


class MealsInput(Model):
    meals: list[Meal] = Field(min_length=1)


class PantryInput(Model):
    item: str = Field(description='Plain name: "rice", "toor dal".')
    qty: float = Field(ge=0, description="0 removes it.")
    unit: Unit


# --- shared -----------------------------------------------------------------------------------


MEAT = ("chicken", "fish", "mutton", "meat", "prawn", "non veg", "non-veg", "nonveg", "seafood", "lamb", "pork", "beef")


NEGATION = re.compile(r"\b(no|not|don'?t|doesn'?t|never|without|nor|avoid)\b[\w\s,]{0,25}$")


def _says(words: str, terms: tuple[str, ...]) -> bool:
    """True if any term appears without a negation just before it ("no meat" doesn't count)."""
    for term in terms:
        for match in re.finditer(re.escape(term), words):
            if not NEGATION.search(words[: match.start()]):
                return True
    return False


def _check_diet(args: MemberInput) -> None:
    """A code check on the diet label against what the user actually said."""
    if not args.diet_confirmed:
        return
    if not args.diet_words:
        raise ToolError("diet_words missing", "Pass the user's exact words about what this person eats.")
    words = args.diet_words.lower()
    if _says(words, MEAT) and args.diet != Diet.NONVEG:
        raise ToolError(f"they said '{args.diet_words}': anyone who eats chicken, fish or meat, even sometimes, is nonveg",
                        "Save this person with diet nonveg.")
    if _says(words, ("egg", "anda")) and args.diet == Diet.VEG:
        raise ToolError(f"they said '{args.diet_words}': eats eggs, so not veg", "Use eggetarian (or nonveg if they eat meat).")


@anyaa_tool("upsert_member", "Add someone who eats at home, or update them (matched by name).", MemberInput)
def upsert_member(args: MemberInput) -> dict:
    _check_diet(args)
    with db() as conn:
        if args.previous_name and queries.get_member(conn, args.previous_name) and not queries.get_member(conn, args.name):
            queries.rename_member(conn, args.previous_name, args.name)
        existing = queries.get_member(conn, args.name)
        spice = args.spice_level if args.spice_level is not None else (existing.spice_level if existing else 2)
        member = queries.save_member(conn, Member(**args.model_dump(exclude={"spice_level", "previous_name", "diet_words"}),
                                                  spice_level=spice))
    _changed()
    return {"member": member.name, "diet": member.diet, "diet_confirmed": member.diet_confirmed}


@anyaa_tool("add_preferences", "Save what the household told you, as notes. All of a turn's facts in one call.", AddPreferencesInput)
def add_preferences(args: AddPreferencesInput) -> dict:
    with db() as conn:
        known = {m.name.lower(): m.name for m in queries.list_members(conn)}
        unknown = sorted({i.member for i in args.items if i.member and i.member.lower() not in known})
        if unknown:
            raise ToolError(f"not household members: {', '.join(unknown)}", "Use a saved member's name, or null for the whole house.")
        saved = [queries.add_preference(conn, Preference(**i.model_dump() | {"member": known[i.member.lower()] if i.member else None}))
                 for i in args.items]
    _changed()
    return {"saved": [f"#{p.id} {p.member or 'household'}: {p.category}" for p in saved]}


@anyaa_tool(
    "park_for_later",
    "Keep something they mentioned that belongs to a different part (an allergy during the family part, the cook's "
    "timings during tastes...), so it's never lost. The right part turns it into a proper note.",
    ParkInput,
)
def park_for_later(args: ParkInput) -> dict:
    with db() as conn:
        known = {m.name.lower(): m.name for m in queries.list_members(conn)}
        member = known.get((args.member or "").lower())
        saved = queries.add_preference(conn, Preference(member=member, category="parked", detail=args.fact,
                                                        strict=False, quote=args.quote))
    _changed()
    return {"parked": f"#{saved.id}", "say": "Acknowledge it in a few words ('noted for later') and stay on this part."}


@anyaa_tool("remove_preference", "Delete a saved note by its #id (for corrections; then add the right one).", RemovePreferenceInput)
def remove_preference(args: RemovePreferenceInput) -> dict:
    with db() as conn:
        if not queries.remove_preference(conn, args.id):
            raise ToolError(f"no note #{args.id}", "Use an id from the household profile.")
    _changed()
    return {"removed": args.id}


# --- FAMILY -----------------------------------------------------------------------------------


@anyaa_tool("remove_member", "Remove someone who doesn't eat at home after all.", RemoveMemberInput)
def remove_member(args: RemoveMemberInput) -> dict:
    with db() as conn:
        if not queries.remove_member(conn, args.name):
            raise ToolError(f"no one called '{args.name}'", "Check the name in the household profile.")
    _changed()
    return {"removed": args.name}


@anyaa_tool("family_done", "Call when everyone who eats at home is saved and each person's diet came from the user.", NoInput)
def family_done(_: NoInput) -> dict:
    with db() as conn:
        people = queries.list_members(conn)
    if not people:
        raise ToolError("nobody is saved yet", "Ask who eats at home.")
    if guessed := [p.name for p in people if not p.diet_confirmed]:
        raise ToolError(f"diet not confirmed by the user for: {', '.join(guessed)}",
                        "Check their diet with the user in one easy question, then save it with diet_confirmed true.")
    return _advance(Phase.FOOD_NEEDS)


# --- FOOD_NEEDS -------------------------------------------------------------------------------

SAFETY_CATEGORIES = {"allergy", "intolerance"}


@anyaa_tool("needs_done", "Call when every person has an answer on allergies or intolerances (even 'none').", NoInput)
def needs_done(_: NoInput) -> dict:
    with db() as conn:
        people = queries.list_members(conn)
        notes = queries.list_preferences(conn)
    answered = {(n.member or "").lower() for n in notes if n.category in SAFETY_CATEGORIES}
    everyone = any(not n.member for n in notes if n.category in SAFETY_CATEGORIES)
    if not everyone and (missing := [p.name for p in people if p.name.lower() not in answered]):
        raise ToolError(f"no allergy answer yet for: {', '.join(missing)}",
                        "Ask once for them, and save category allergy with detail 'none' if there's nothing.")
    return _advance(Phase.TASTES)


# --- TASTES -----------------------------------------------------------------------------------


@anyaa_tool("tastes_done", "Call when you know their everyday food style and at least one thing they love.", NoInput)
def tastes_done(_: NoInput) -> dict:
    with db() as conn:
        notes = queries.list_preferences(conn)
    if not any(n.category in {"cuisine", "routine", "favourite"} for n in notes):
        raise ToolError("nothing saved about what they eat or love", "Save their everyday food style or a favourite first.")
    return _advance(Phase.KITCHEN)


# --- KITCHEN ----------------------------------------------------------------------------------


@anyaa_tool("set_cook_profile", "Save the cook's details, or that the family cooks. Only the fields you pass change.", CookInput)
def set_cook_profile(args: CookInput) -> dict:
    with db() as conn:
        saved = queries.get_cook(conn)
        merged = (saved.model_dump() if saved else {}) | args.model_dump(exclude_unset=True, exclude_none=True)
        try:
            cook = CookProfile.model_validate(merged)
        except ValueError as error:
            raise ToolError(str(error), "Give at least one visit, or set household_cooks true.") from error
        queries.save_cook(conn, cook)
    _changed()
    return {"cook": cook.name or ("family cooks" if cook.household_cooks else "saved"), "phone_saved": bool(cook.phone)}


@anyaa_tool("connect_cook", "After saving the cook's phone: says hello on Telegram if they're connected, else returns the link.", NoInput)
async def connect_cook(_: NoInput) -> dict:
    with db() as conn:
        cook = queries.get_cook(conn)
        contact = telegram.find_contact(conn, phone=cook.phone) if cook and cook.phone else None
    if not cook or not cook.phone:
        raise ToolError("no phone saved for the cook", "Save it with set_cook_profile first.")
    if not telegram.enabled():
        return {"connected": False, "note": "Telegram isn't set up; carry on."}
    if contact is None:
        return {"connected": False, "link_on_screen": await telegram.bot_link()}
    await telegram.send(cook.phone, f"Namaste {cook.name or 'ji'}! I'm Anyaa. I'll send you the menu and a short voice "
                                    "note here before every visit, so you always know what to make. 🙏")
    return {"connected": True, "said_hello": True}


@anyaa_tool("set_household_meals", "Which meals to plan every day, once the user agreed.", MealsInput)
def set_household_meals(args: MealsInput) -> dict:
    with db() as conn:
        queries.set_meals(conn, args.meals)
    _changed()
    return {"meals": [m.value for m in args.meals]}


@anyaa_tool("set_pantry_item", "Record a staple already at home.", PantryInput)
def set_pantry_item(args: PantryInput) -> dict:
    with db() as conn:
        queries.set_pantry_item(conn, PantryItem(item=args.item, qty=args.qty, unit=args.unit))
    return {"pantry": f"{args.item} {args.qty:g}{args.unit.value}"}


@anyaa_tool("kitchen_done", "Call when the cook (or 'the family cooks') and the meals to plan are saved.", NoInput)
def kitchen_done(_: NoInput) -> dict:
    with db() as conn:
        cook = queries.get_cook(conn)
        household = queries.get_household(conn)
    if cook is None:
        raise ToolError("the cook isn't saved", "Save the cook's visits, or that the family cooks.")
    if not household.meals_set:
        raise ToolError("meals to plan aren't agreed", "Propose the meals from the cook's visits and save them once they agree.")
    return _advance(Phase.CONFIRM)


# --- CONFIRM ----------------------------------------------------------------------------------


@anyaa_tool("check_instamart", "Whether Instamart is connected, so groceries can be ordered later.", NoInput)
def check_instamart(_: NoInput) -> dict:
    return {"connected": swiggy.logged_in(), "delivery_address_chosen": swiggy.selected_address() is not None}


@anyaa_tool("read_back_profile", "Everything noted so far, to summarise for the user before confirming.", NoInput)
def read_back_profile(_: NoInput) -> dict:
    global _summary_current
    _summary_current = True
    with db() as conn:
        return {"facts": profile.facts(conn),
                "say": "Summarise using ONLY these facts, diets exactly as written. Never add, merge or change one."}


@anyaa_tool("confirm_profile", "Call only after the user agreed the summary is right. Moves on to meal planning.", NoInput)
def confirm_profile(_: NoInput) -> dict:
    with db() as conn:
        parked = [p for p in queries.list_preferences(conn) if p.category == "parked"]
    if parked:
        raise ToolError(f"{len(parked)} parked note(s) still unsorted: {'; '.join(p.detail for p in parked)}",
                        "Save each as a proper note (or into the cook profile), remove the parked one, then read back.")
    if not _summary_current:
        raise ToolError("the summary wasn't read out since the last change", "Call read_back_profile, summarise it, get a yes.")
    with db() as conn:
        queries.confirm_profile(conn)
    planner.start_in_background()  # today and tomorrow are being planned while Anyaa wraps up
    return _advance(Phase.MEAL_PLAN)


FAMILY_TOOLS = [upsert_member, remove_member, park_for_later, family_done]
NEEDS_TOOLS = [add_preferences, remove_preference, upsert_member, park_for_later, needs_done]
TASTES_TOOLS = [add_preferences, remove_preference, park_for_later, tastes_done]
KITCHEN_TOOLS = [set_cook_profile, connect_cook, set_household_meals, set_pantry_item, remove_preference, park_for_later,
                 kitchen_done]
CONFIRM_TOOLS = [check_instamart, read_back_profile, confirm_profile, add_preferences, remove_preference, upsert_member,
                 set_cook_profile]
