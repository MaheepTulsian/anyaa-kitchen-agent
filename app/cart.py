"""Turns an approved plan's grocery list into an Instamart cart and a sabziwala WhatsApp list.

1. Search Instamart for every grocery line (in parallel).
2. One LLM call picks the product and pack count per line (and respects strict notes).
3. Fill the cart (replaces the user's Instamart cart; never checks out).
4. Fresh produce, plus anything Instamart didn't have, goes on a wa.me link for the sabziwala.
"""

import asyncio
import sqlite3
from pathlib import Path
from urllib.parse import quote

from pydantic import Field

from app import instamart, llm, profile, swiggy
from app.instamart import CartLine
from app.models import GroceryLine, MealPlan, Model

PROMPT = (Path(__file__).parent / "prompts" / "cart_pick.md").read_text(encoding="utf-8")


class Pick(Model):
    item: str
    product_id: str | None  # None when nothing suitable is in stock
    quantity: int = Field(ge=1, default=1)


class Picks(Model):
    picks: list[Pick]


class CartSummary(Model):
    mode: str  # "mock" | "mcp"
    items: list[str]  # "Tata Sampann Toor Dal 1 kg × 1"
    total: float
    sabziwala: list[str]  # "onion 1 kg"
    sabziwala_link: str


def whatsapp_link(lines: list[str]) -> str:
    text = "Bhaiya, please send:\n" + "\n".join(f"- {line}" for line in lines)
    return f"https://wa.me/?text={quote(text)}"


async def _pick(conn: sqlite3.Connection, client, wanted: list[GroceryLine]) -> list[Pick]:
    """Search each line and let one LLM call choose the product and pack count."""
    limit = asyncio.Semaphore(4)

    async def search(line: GroceryLine) -> list[instamart.Product]:
        async with limit:
            return await client.search(line.item)

    results = await asyncio.gather(*(search(g) for g in wanted))
    options = "\n\n".join(
        f"{g.item} — need {g.quantity}\n" + "\n".join(
            f"  {p.id} | {p.name} | {p.pack} | ₹{p.price:g} | {'in stock' if p.in_stock else 'OUT'}" for p in found[:5])
        for g, found in zip(wanted, results, strict=True)
    )
    picks = await llm.ask(Picks, system=PROMPT, prompt=f"HOUSEHOLD\n{profile.render(conn)}\n\nGROCERIES\n{options}")
    return picks.picks


async def _serviceable(job):
    """POC assumption: the address is always serviceable. When Swiggy says it isn't right now (late night, store
    closed), the same job runs on the mock catalog so the flow carries on; it's logged, never hidden."""
    try:
        return await job(instamart.get_client())
    except swiggy.InstamartError as error:
        if "serviceable" not in str(error).lower():
            raise
        print(f"instamart not serviceable right now, using the mock cart: {error}")
        return await job(instamart.MockInstamart())


async def add_items(conn: sqlite3.Connection, items: list[str]) -> CartSummary:
    """Add a few things (e.g. what the cook says is running low) to the existing Instamart cart."""
    return await _serviceable(lambda client: _add_items(conn, client, items))


async def fill(conn: sqlite3.Connection, plan: MealPlan) -> CartSummary:
    """The week's groceries into the cart (replaces it), the rest on the sabziwala list."""
    return await _serviceable(lambda client: _fill(conn, client, plan))


async def _add_items(conn: sqlite3.Connection, client, items: list[str]) -> CartSummary:
    wanted = [GroceryLine(item=item, quantity="1 regular pack", where="instamart") for item in items]
    chosen = [p for p in await _pick(conn, client, wanted) if p.product_id]
    cart = await client.add_to_cart([CartLine(product_id=p.product_id, quantity=p.quantity) for p in chosen])
    missing = [g.item for g in wanted if g.item not in {p.item for p in chosen}]
    return CartSummary(mode=cart.mode, items=[f"{i.product.name} {i.product.pack} × {i.quantity}" for i in cart.items],
                       total=cart.total, sabziwala=missing, sabziwala_link=whatsapp_link(missing))


async def _fill(conn: sqlite3.Connection, client, plan: MealPlan) -> CartSummary:
    wanted = [g for g in plan.groceries if g.where == "instamart"]
    sabzi = [g for g in plan.groceries if g.where == "sabziwala"]
    picks = await _pick(conn, client, wanted)
    chosen = [p for p in picks if p.product_id]
    cart = await client.build_cart([CartLine(product_id=p.product_id, quantity=p.quantity) for p in chosen])
    missing = {p.item for p in picks if not p.product_id} | {
        p.item for p in chosen if p.product_id in cart.unavailable}
    for_sabziwala = [f"{g.item} {g.quantity}" for g in sabzi] + [f"{g.item} {g.quantity}" for g in wanted if g.item in missing]

    return CartSummary(
        mode=cart.mode,
        items=[f"{i.product.name} {i.product.pack} × {i.quantity}" for i in cart.items],
        total=cart.total,
        sabziwala=for_sabziwala,
        sabziwala_link=whatsapp_link(for_sabziwala),
    )
