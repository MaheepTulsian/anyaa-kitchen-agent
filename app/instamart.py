"""Instamart: search products and fill the cart. Never places an order.

Two implementations of the same interface: a deterministic mock (default, data/mock_instamart.json)
and the real Swiggy Instamart through its MCP tools. `get_client()` picks one.
"""

import json
from typing import Protocol

from pydantic import Field

from app import config, swiggy
from app.models import Model

MOCK_CATALOG = config.DATA_DIR / "mock_instamart.json"

# Products seen in Swiggy search, keyed by our product id, so the cart can show names and limits.
_seen: dict[str, tuple["Product", int]] = {}


class Product(Model):
    id: str
    name: str
    brand: str | None = None
    pack: str  # human-readable pack size, e.g. "1 kg", "500 ml", "6 pcs"
    price: float  # ₹
    in_stock: bool = True


class CartLine(Model):
    product_id: str
    quantity: int = Field(ge=1)


class CartItem(Model):
    product: Product
    quantity: int
    line_total: float


class CartResult(Model):
    mode: str  # "mock" | "mcp"
    items: list[CartItem] = []
    total: float = 0
    unavailable: list[str] = []  # product ids that could not be added
    note: str = "Cart only. Review and pay in the Swiggy app."


class InstamartClient(Protocol):
    async def search(self, query: str) -> list[Product]: ...

    async def build_cart(self, lines: list[CartLine]) -> CartResult: ...

    async def add_to_cart(self, lines: list[CartLine]) -> CartResult:
        """Add to what's already in the cart, instead of replacing it."""
        ...


def get_client() -> InstamartClient:
    """Real Swiggy when INSTAMART_MODE=mcp and logged in; otherwise the mock."""
    if config.INSTAMART_MODE == "mcp" and swiggy.logged_in():
        return SwiggyInstamart()
    return MockInstamart()


# --- mock -------------------------------------------------------------------------------------


class MockInstamart:
    def __init__(self) -> None:
        self.rows = json.loads(MOCK_CATALOG.read_text(encoding="utf-8"))
        self.products = {row["id"]: Product.model_validate(_product_fields(row)) for row in self.rows}

    async def search(self, query: str) -> list[Product]:
        """Rank by how many query words appear in the name, brand or keywords."""
        words = query.lower().replace("_", " ").split()
        scored = []
        for row in self.rows:
            haystack = " ".join([row["name"], row.get("brand") or "", *row["keywords"]]).lower()
            score = sum(word in haystack for word in words)
            if score:
                scored.append((score, row["price"], row["id"]))
        scored.sort(key=lambda s: (-s[0], s[1]))  # best match first, then cheapest
        return [self.products[product_id] for _, _, product_id in scored[:5]]

    async def build_cart(self, lines: list[CartLine]) -> CartResult:
        items, unavailable = [], []
        for line in lines:
            product = self.products.get(line.product_id)
            if product is None or not product.in_stock:
                unavailable.append(line.product_id)
                continue
            items.append(
                CartItem(
                    product=product,
                    quantity=line.quantity,
                    line_total=round(product.price * line.quantity, 2),
                )
            )
        total = round(sum(item.line_total for item in items), 2)
        return CartResult(mode="mock", items=items, total=total, unavailable=unavailable)

    async def add_to_cart(self, lines: list[CartLine]) -> CartResult:
        return await self.build_cart(lines)  # the mock keeps no cart between calls


def _product_fields(row: dict) -> dict:
    return {key: row[key] for key in ("id", "name", "brand", "pack", "price", "in_stock") if key in row}


# --- real Swiggy ------------------------------------------------------------------------------


class SwiggyInstamart:
    """Real Instamart through Swiggy's MCP tools (search_products, update_cart, get_cart)."""

    async def add_to_cart(self, lines: list[CartLine]) -> CartResult:
        return await _add_to_swiggy_cart(self, lines)

    async def search(self, query: str) -> list[Product]:
        data = await swiggy.call_tool("search_products", {"addressId": swiggy.require_address(), "query": query})
        products = []
        for item in data.get("products", []):
            for variant in item.get("variations", []):
                product = Product(
                    id=f"{variant['spinId']}:{variant.get('skuId', '')}",
                    name=variant.get("displayName") or item.get("displayName", ""),
                    brand=variant.get("brandName") or item.get("brand"),
                    pack=variant.get("quantityDescription", ""),
                    price=float(variant["price"]["offerPrice"]),
                    in_stock=bool(variant.get("isInStockAndAvailable")),
                )
                _seen[product.id] = (product, int(variant.get("maxQuantity") or 99))
                products.append(product)
        return products[:10]

    async def build_cart(self, lines: list[CartLine]) -> CartResult:
        """Replaces the Instamart cart with these lines (cart only; never checks out)."""
        items, cart_items, unavailable = [], [], []
        for line in lines:
            if line.product_id not in _seen:
                unavailable.append(line.product_id)  # unknown id: search for it first
                continue
            product, max_quantity = _seen[line.product_id]
            quantity = min(line.quantity, max_quantity)
            spin_id, sku_id = line.product_id.split(":", 1)
            items.append({"spinId": spin_id, "skuId": sku_id, "quantity": quantity})
            cart_items.append(
                CartItem(product=product, quantity=quantity, line_total=product.price * quantity)
            )

        if items:
            await swiggy.call_tool("update_cart", {"selectedAddressId": swiggy.require_address(), "items": items})
        cart = await swiggy.call_tool("get_cart", {})
        to_pay = cart.get("billBreakdown", {}).get("toPay", {}).get("value") or cart.get("cartTotalAmount")
        return CartResult(
            mode="mcp",
            items=cart_items,
            total=_rupees(to_pay, default=sum(i.line_total for i in cart_items)),
            unavailable=unavailable,
            note="Added to your Instamart cart. Review and pay in the Swiggy app.",
        )


async def _current_cart_lines() -> list[dict]:
    """What's in the Swiggy cart now, as update_cart items. Raises if it can't be read safely."""
    cart = await swiggy.call_tool("get_cart", {})
    lines = []
    for item in cart.get("items", []):
        spin = item.get("spinId") or item.get("spin_id") or (item.get("variation") or {}).get("spinId")
        quantity = item.get("quantity") or item.get("qty") or item.get("count")
        if not spin or not quantity:
            raise swiggy.InstamartError("couldn't read the current cart safely, so it wasn't changed")
        lines.append({"spinId": spin, "skuId": item.get("skuId", ""), "quantity": int(quantity)})
    return lines


async def _add_to_swiggy_cart(client: "SwiggyInstamart", lines: list[CartLine]) -> CartResult:
    existing = await _current_cart_lines()
    added = []
    for line in lines:
        if line.product_id not in _seen:
            continue
        spin_id, sku_id = line.product_id.split(":", 1)
        product, max_quantity = _seen[line.product_id]
        match = next((e for e in existing if e["spinId"] == spin_id), None)
        if match:
            match["quantity"] = min(match["quantity"] + line.quantity, max_quantity)
        else:
            existing.append({"spinId": spin_id, "skuId": sku_id, "quantity": min(line.quantity, max_quantity)})
        added.append(CartItem(product=product, quantity=line.quantity, line_total=product.price * line.quantity))
    if added:
        await swiggy.call_tool("update_cart", {"selectedAddressId": swiggy.require_address(), "items": existing})
    return CartResult(mode="mcp", items=added, total=sum(i.line_total for i in added),
                      note="Added to your Instamart cart, alongside what was already there.")


def _rupees(value: object, default: float) -> float:
    try:
        return float(str(value).replace("₹", "").replace(",", "").strip())
    except ValueError:
        return round(default, 2)
