"""Cook agent tools (Telegram conversation during and around visits).

The cook can report things and ask for help. Any change to the menu goes through the planner, which
re-runs the safety check; if no safe fix exists, the household is asked to pick A or B. The cook side
can never change a strict rule, and never sees anyone's health details.
"""


from pydantic import Field

from app import bridge, cart, clock, llm, planner, queries, swiggy
from app.db import db
from app.models import Escalation, Model, Preference
from app.tools import ToolError, anyaa_tool


class NoInput(Model):
    pass


class MissingInput(Model):
    item: str = Field(description='What ran out or isn\'t there: "paneer", "curd", "atta".')


class LateInput(Model):
    minutes: int = Field(ge=0, le=600, description="How late, roughly, in minutes.")


class StockInput(Model):
    items: list[str] = Field(min_length=1, description='Things finished or running low: ["atta", "onion"].')


class FeedbackInput(Model):
    dish: str
    feedback: str = Field(description='What happened, in plain words: "Sushil left most of it", "both loved it".')
    member: str | None = Field(None, description="Who, if the cook named someone.")


class LeftoverInput(Model):
    what: str = Field(description='"half the dal from lunch", "2 rotis".')


class HelpInput(Model):
    dish: str


class AskInput(Model):
    question: str = Field(description="What the family needs to decide, in one plain sentence.")
    option_a: str
    option_b: str


def _uses(meal, item: str) -> bool:
    words = item.lower().split()
    text = " ".join(f"{d.name} {' '.join(d.ingredients)}" for d in meal.dishes).lower()
    return any(w in text for w in words)


async def _swap_one(conn, meal, why: str) -> dict:
    """Re-plan exactly one meal. Code, not the model, decides which meal may change."""
    stored = queries.get_plan(conn)
    label = bridge.describe(conn, meal).split(":")[0]
    changed = await planner.change(conn, stored, (
        f"Change ONLY {meal.day:%A} {meal.meal} ({label}). {why} The cook is in the kitchen now, so the new dish "
        "must be makeable right away from a normal home kitchen: no soaking, no overnight prep. Keep every other "
        "dish of that meal and every other meal exactly as it is. Keep it safe for everyone."))
    new = next((m for m in changed.plan.meals if (m.day, m.meal) == (meal.day, meal.meal)), None)
    if changed.issues or new is None:
        queries.save_plan(conn, stored)  # planner.change saved a draft; put the agreed plan back
        return {"safe_fix_found": False, "problems": [i.problem for i in changed.issues] or ["no workable swap"]}
    meals = [new if (m.day, m.meal) == (meal.day, meal.meal) else m for m in stored.plan.meals]
    queries.save_plan(conn, stored.model_copy(update={"plan": stored.plan.model_copy(update={"meals": meals})}))
    notes = [f"{d.name}: {d.cook_note}" for d in new.dishes if d.cook_note]
    return {"safe_fix_found": True, "meal": bridge.describe(conn, new), "cook_notes": notes}


async def _cart_sentence(conn, items: list[str]) -> tuple[str, dict]:
    """Add items to the Instamart cart (never replacing it); a sentence for the family about how it went."""
    things = ", ".join(items)
    try:
        added = await cart.add_items(conn, items)
    except (swiggy.InstamartError, swiggy.OAuthError, llm.LLMError) as error:
        for item in items:
            queries.add_preference(conn, Preference(category="restock", detail=item, strict=False, quote=f"cook: {item}"))
        return (f"I couldn't reach your Instamart cart ({error}), so please order {things} when you can. "
                "It's on next week's list too."), {"in_cart": False}
    sentence = ""
    if added.items:
        sentence = (f"I've added {', '.join(added.items)} to your Instamart cart (about ₹{added.total:.0f}"
                    "). Please place the order in Swiggy.")
    if added.sabziwala:
        sentence += f" Couldn't find {', '.join(added.sabziwala)} on Instamart; please pick it up locally."
    return sentence.strip(), {"in_cart": added.items, "not_found": added.sabziwala}


@anyaa_tool("todays_menu", "The next meals the cook is making (not ones already cooked), with notes per dish.", NoInput)
def todays_menu(_: NoInput) -> dict:
    with db() as conn:
        stored = queries.get_plan(conn)
        meals = bridge.upcoming(conn, stored.plan)[:3] if stored else []
        if not meals:
            return {"menu": "nothing planned yet"}
        return {"menu": [bridge.describe(conn, m) + "".join(
                    f" | {d.name} for {bridge.for_cook(conn, d.for_whom)}" + (f", note: {d.cook_note}" if d.cook_note else "")
                    for d in m.dishes) for m in meals],
                "say": "Dish names only. No cooking steps unless they ask how to make something."}


@anyaa_tool("dish_help", "Ingredients and the cook notes for one dish on the menu, to explain how to make it.", HelpInput)
def dish_help(args: HelpInput) -> dict:
    with db() as conn:
        stored = queries.get_plan(conn)
        for meal in bridge.upcoming(conn, stored.plan) if stored else []:
            for dish in meal.dishes:
                if args.dish.lower() in dish.name.lower():
                    return {"dish": dish.name, "for": dish.for_whom, "ingredients": dish.ingredients, "note": dish.cook_note}
    raise ToolError(f"'{args.dish}' isn't on the next few meals", "Ask which dish they mean.")


@anyaa_tool("report_missing", "Something needed for the next meal ran out. Swaps that meal safely, tells the family, "
                              "adds the item to the Instamart cart.", MissingInput)
async def report_missing(args: MissingInput) -> dict:
    with db() as conn:
        stored = queries.get_plan(conn)
        if stored is None:
            raise ToolError("there's no plan yet", "Tell the cook you'll check with the family.")
        coming = bridge.upcoming(conn, stored.plan)
        target = next((m for m in coming[:3] if _uses(m, args.item)), None)
        who = bridge.cook_name(conn)
        cart_line, restock = await _cart_sentence(conn, [args.item])
        if target is None:
            bridge.tell_family(conn, f"{who} says {args.item} has run out. The next meals don't need it. {cart_line}")
            return {"swap_needed": False, "tell_cook": "The next meals don't need it; carry on as planned.", **restock}
        result = await _swap_one(conn, target, f"The cook says {args.item} has run out.")
        if result["safe_fix_found"]:
            bridge.tell_family(conn, f"Heads up: {who} says {args.item} has run out, so {result['meal']}. {cart_line}")
            result["tell_cook"] = f"Make this instead, {result['meal']}"
        else:
            bridge.tell_family(conn, f"{who} says {args.item} has run out for {bridge.describe(conn, target)}. {cart_line}")
            result["next"] = "No safe swap: call ask_household with two clear options."
    return {**result, **restock, "family_told": True}


@anyaa_tool("report_late", "The cook is running late. Swaps the next meal for something quicker if needed.", LateInput)
async def report_late(args: LateInput) -> dict:
    with db() as conn:
        if args.minutes < 30:
            return {"swap_needed": False}
        stored = queries.get_plan(conn)
        coming = bridge.upcoming(conn, stored.plan) if stored else []
        if not coming:
            return {"swap_needed": False}
        result = await _swap_one(conn, coming[0], f"The cook is {args.minutes} minutes late; make it a quick 20-minute "
                                                  "version, same spirit.")
        if result["safe_fix_found"]:
            bridge.tell_family(conn, f"{bridge.cook_name(conn)} is running about {args.minutes} minutes late, so I've "
                                     f"made it quicker: {result['meal']}.")
            result["tell_cook"] = f"No problem. Make it quick: {result['meal']}"
    return result


@anyaa_tool("report_absent", "The cook can't come. Tells the family and asks them to pick a plan B.", NoInput)
def report_absent(_: NoInput) -> dict:
    with db() as conn:
        esc = queries.add_escalation(conn, Escalation(
            question="The cook can't come today.",
            option_a="Switch today to simple 20-minute meals you can make yourselves",
            option_b="Order in today and keep the plan for tomorrow"))
        bridge.tell_family(conn, f"The cook can't make it today. Should I (A) switch today to simple 20-minute meals you "
                              f"can make, or (B) leave today for ordering in and keep the plan for tomorrow? [question {esc.id}]")
    return {"family_asked": True}


@anyaa_tool("report_stock", "Things finished or running low: adds them to the Instamart cart and asks the family to order.", StockInput)
async def report_stock(args: StockInput) -> dict:
    with db() as conn:
        cart_line, restock = await _cart_sentence(conn, args.items)
        verb = "is" if len(args.items) == 1 else "are"
        bridge.tell_family(conn, f"{bridge.cook_name(conn)} says {', '.join(args.items)} {verb} running low. {cart_line}")
    return {**restock, "family_told": True, "tell_cook": "The family has been asked to order it."}


@anyaa_tool("report_leftovers", "Food left over, so the planner can use it.", LeftoverInput)
def report_leftovers(args: LeftoverInput) -> dict:
    with db() as conn:
        queries.add_preference(conn, Preference(category="leftovers", detail=f"{args.what} (as of {clock.now(conn):%a %H:%M})",
                                                strict=False, quote=f"cook: {args.what}"))
    return {"noted": True}


@anyaa_tool("report_feedback", "How a dish went down (eaten, left, loved). Shapes future plans.", FeedbackInput)
def report_feedback(args: FeedbackInput) -> dict:
    with db() as conn:
        names = {m.name.lower(): m.name for m in queries.list_members(conn)}
        member = names.get((args.member or "").lower())
        queries.add_preference(conn, Preference(member=member, category="feedback", strict=False,
                                                detail=f"{args.dish}: {args.feedback}", quote=f"cook: {args.feedback}"))
    return {"noted": True}


@anyaa_tool("ask_household", "When you can't safely settle something yourself: the family picks A or B.", AskInput)
def ask_household(args: AskInput) -> dict:
    with db() as conn:
        esc = queries.add_escalation(conn, Escalation(question=args.question, option_a=args.option_a, option_b=args.option_b))
        bridge.tell_family(conn, f"{args.question} Should I (A) {args.option_a}, or (B) {args.option_b}? [question {esc.id}]")
    return {"family_asked": True, "tell_cook": "You'll let them know as soon as the family answers."}


COOK_TOOLS = [todays_menu, dish_help, report_missing, report_late, report_absent, report_stock, report_leftovers,
              report_feedback, ask_household]
