"""Onboarding tools: every fact the household shares is stored through one of these."""

from pydantic import Field

from app.integrations import instamart_mcp, swiggy_oauth
from app.models import (
    AgeGroup,
    Constraint,
    ConstraintKind,
    CookProfile,
    CookVisit,
    Diet,
    Meal,
    Member,
    Model,
    PantryItem,
    Phase,
    Strength,
    Unit,
    Weekday,
)
from app.services.profile import onboarding_gaps, render_profile
from app.store import constraints, cook, households, members, pantry
from app.tools.base import Tool, ToolContext, ToolError

DEFAULT_STRENGTH = {
    ConstraintKind.ALLERGEN: Strength.HARD,
    ConstraintKind.DIET_DAY: Strength.HARD,
    ConstraintKind.FASTING: Strength.HARD,
    ConstraintKind.HOUSEHOLD_RULE: Strength.HARD,
    ConstraintKind.AVOID_INGREDIENT: Strength.SOFT,
    ConstraintKind.HEALTH_SIGNAL: Strength.SOFT,
    ConstraintKind.FAVOURITE: Strength.SOFT,
    ConstraintKind.DISLIKE_DISH: Strength.SOFT,
}

# Households whose profile was read back with no changes since. Any write clears the flag,
# so confirm_profile always follows a fresh read-back.
_read_back_current: set[int] = set()


def _changed(ctx: ToolContext) -> None:
    _read_back_current.discard(ctx.household_id)


def _member_id(ctx: ToolContext, name: str) -> int:
    member = members.get_member_by_name(ctx.conn, ctx.household_id, name)
    if member is None or member.id is None:
        raise ToolError(f"no household member called '{name}'", "Call upsert_member for them first.")
    return member.id


# --- inputs -----------------------------------------------------------------------------------


class UpsertMemberInput(Model):
    name: str = Field(description='What the family calls them: "Papa", "Dadi", "Riya".')
    relation: str | None = Field(None, description="e.g. father, grandmother, daughter, flatmate")
    age_group: AgeGroup
    diet: Diet
    spice_level: int | None = Field(None, ge=0, le=4, description="0 none .. 4 very spicy")


class RemoveMemberInput(Model):
    name: str


class SetConstraintInput(Model):
    member: str | None = Field(None, description="Member name, or null for a whole-household rule.")
    kind: ConstraintKind
    value: str = Field(
        description='What the rule is about, e.g. "peanut", "sabudana", "diabetic_friendly", '
        '"veg", "no_onion_garlic", "ekadashi". Use "none" with kind=allergen for no allergies.'
    )
    strength: Strength | None = Field(None, description="Omit to use the default for the kind.")
    scope: str | None = Field(
        None, description='Allergen: "trace" or "ingredient". Day rules: weekday like "tue".'
    )
    condition: str | None = Field(None, description='Exception in words, e.g. "unless guests".')
    quote: str = Field(description="The user's exact words this came from.")


class VisitInput(Model):
    label: str = Field(description='e.g. "morning", "evening"')
    start: str = Field(description="24h time HH:MM, e.g. 07:30")
    minutes: int = Field(gt=0, le=480)
    meals: list[Meal] = Field(min_length=1)


class SetCookProfileInput(Model):
    name: str | None = None
    household_cooks: bool = Field(False, description="True if there is no cook and the family cooks.")
    visits: list[VisitInput] = []
    days_off: list[Weekday] = []
    known_dishes: list[str] = []
    notes: str | None = None


class SetMealsInput(Model):
    meals: list[Meal] = Field(min_length=1)


class SetPantryItemInput(Model):
    item: str = Field(description='Plain name, e.g. "rice", "toor dal".')
    qty: float = Field(ge=0, description="0 removes it.")
    unit: Unit


class NoInput(Model):
    pass


class ChooseAddressInput(Model):
    address_id: str


# --- handlers ---------------------------------------------------------------------------------


def upsert_member(ctx: ToolContext, args: UpsertMemberInput) -> dict:
    existing = members.get_member_by_name(ctx.conn, ctx.household_id, args.name)
    spice = args.spice_level if args.spice_level is not None else (existing.spice_level if existing else 2)
    member = members.upsert_member(
        ctx.conn,
        ctx.household_id,
        Member(name=args.name, relation=args.relation, age_group=args.age_group, diet=args.diet, spice_level=spice),
    )
    _changed(ctx)
    return {"member": member.name, "updated": existing is not None}


def remove_member(ctx: ToolContext, args: RemoveMemberInput) -> dict:
    if not members.deactivate_member(ctx.conn, ctx.household_id, args.name):
        raise ToolError(f"no household member called '{args.name}'", "Check the name and try again.")
    _changed(ctx)
    return {"removed": args.name}


def set_constraint(ctx: ToolContext, args: SetConstraintInput) -> dict:
    member_id = _member_id(ctx, args.member) if args.member else None
    if args.kind is ConstraintKind.ALLERGEN and args.value.lower() != "none" and args.scope not in ("trace", "ingredient"):
        raise ToolError(
            "allergen scope missing",
            'Ask whether traces (oil, garnish) matter, then set scope "trace" or "ingredient".',
        )
    result = constraints.add_constraint(
        ctx.conn,
        ctx.household_id,
        Constraint(
            member_id=member_id,
            kind=args.kind,
            value=args.value.strip().lower(),
            strength=args.strength or DEFAULT_STRENGTH[args.kind],
            scope=args.scope,
            condition=args.condition,
            quote=args.quote,
        ),
    )
    _changed(ctx)
    return {"saved": f"{args.member or 'household'}: {args.kind.value} {args.value}", "replaced_previous": result.superseded_id is not None}


def set_cook_profile(ctx: ToolContext, args: SetCookProfileInput) -> dict:
    try:
        profile = CookProfile(
            name=args.name,
            household_cooks=args.household_cooks,
            visits=[CookVisit.model_validate(v.model_dump()) for v in args.visits],
            days_off=args.days_off,
            known_dishes=args.known_dishes,
            notes=args.notes,
        )
    except ValueError as error:
        raise ToolError(str(error), "Give at least one visit, or set household_cooks=true.") from error
    cook.set_cook_profile(ctx.conn, ctx.household_id, profile)
    _changed(ctx)
    return {"cook": profile.name or ("family cooks" if profile.household_cooks else "saved")}


def set_household_meals(ctx: ToolContext, args: SetMealsInput) -> dict:
    households.set_meals(ctx.conn, ctx.household_id, args.meals)
    _changed(ctx)
    return {"meals": [m.value for m in args.meals]}


def set_pantry_item(ctx: ToolContext, args: SetPantryItemInput) -> dict:
    pantry.set_pantry_item(ctx.conn, ctx.household_id, PantryItem(item=args.item, qty=args.qty, unit=args.unit))
    return {"pantry": f"{args.item} {args.qty:g}{args.unit.value}"}


def get_onboarding_gaps(ctx: ToolContext, _: NoInput) -> dict:
    return onboarding_gaps(ctx.conn, ctx.household_id).model_dump()


def read_back_profile(ctx: ToolContext, _: NoInput) -> dict:
    _read_back_current.add(ctx.household_id)
    return {"profile": render_profile(ctx.conn, ctx.household_id)}


def confirm_profile(ctx: ToolContext, _: NoInput) -> dict:
    gaps = onboarding_gaps(ctx.conn, ctx.household_id)
    if gaps.required:
        raise ToolError(f"still missing: {'; '.join(gaps.required)}", "Ask about these first.")
    if ctx.household_id not in _read_back_current:
        raise ToolError("profile not read back since the last change", "Call read_back_profile, summarise it, and get a yes.")
    households.set_profile_confirmed(ctx.conn, ctx.household_id, True)
    households.set_phase(ctx.conn, ctx.household_id, Phase.PLANNING)
    return {"confirmed": True, "next_phase": Phase.PLANNING.value}


def instamart_status(ctx: ToolContext, _: NoInput) -> dict:
    return {"connected": swiggy_oauth.load_token() is not None, "address_chosen": instamart_mcp.selected_address() is not None}


async def list_instamart_addresses(ctx: ToolContext, _: NoInput) -> dict:
    try:
        addresses = await instamart_mcp.list_addresses()
    except (swiggy_oauth.OAuthError, instamart_mcp.InstamartError) as error:
        raise ToolError(str(error), "Ask them to tap Connect Instamart on screen first.") from error
    return {"addresses": [a.model_dump() for a in addresses]}


async def choose_instamart_address(ctx: ToolContext, args: ChooseAddressInput) -> dict:
    addresses = {a.id: a for a in await instamart_mcp.list_addresses()}
    if args.address_id not in addresses:
        raise ToolError("unknown address id", "Call list_instamart_addresses and use one of those ids.")
    instamart_mcp.select_address(addresses[args.address_id])
    return {"delivering_to": addresses[args.address_id].tag}


ONBOARDING_TOOLS = [
    Tool("upsert_member", "Add a household member or update one (matched by name).", UpsertMemberInput, upsert_member),
    Tool("remove_member", "Remove someone who no longer eats at home.", RemoveMemberInput, remove_member),
    Tool("set_constraint", "Store an allergy, diet day, fast, health signal, like/dislike or household rule. A new rule replaces an older one about the same thing.", SetConstraintInput, set_constraint),
    Tool("set_cook_profile", "Store the cook's name, visits, days off and dishes they know, or that the family cooks.", SetCookProfileInput, set_cook_profile),
    Tool("set_household_meals", "Which meals the household wants planned.", SetMealsInput, set_household_meals),
    Tool("set_pantry_item", "Record a staple already at home.", SetPantryItemInput, set_pantry_item),
    Tool("get_onboarding_gaps", "What is still missing (required) or nice to know (optional).", NoInput, get_onboarding_gaps),
    Tool("read_back_profile", "The current profile as text, to summarise aloud before confirming.", NoInput, read_back_profile),
    Tool("confirm_profile", "Lock the profile after the user agreed to the read-back. Moves on to meal planning.", NoInput, confirm_profile),
    Tool("instamart_status", "Whether Instamart is connected and a delivery address is chosen.", NoInput, instamart_status),
    Tool("list_instamart_addresses", "The user's saved Swiggy addresses (id and label).", NoInput, list_instamart_addresses),
    Tool("choose_instamart_address", "Set which saved address groceries are delivered to.", ChooseAddressInput, choose_instamart_address),
]
