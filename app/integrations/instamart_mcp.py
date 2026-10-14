"""Real Instamart via Swiggy's MCP server (streamable HTTP + OAuth bearer token).

Only an allowlist of read and cart tools can be called. Checkout, payment, order and address
changes are refused here, so the agent can never place an order or edit the user's account.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app import config
from app.integrations import swiggy_oauth
from app.integrations.instamart import CartItem, CartLine, CartResult, Product
from app.models import Model

ALLOWED_TOOLS = {"get_addresses", "search_products", "your_go_to_items", "get_cart", "update_cart"}
ADDRESS_PATH = config.DATA_DIR / "swiggy_address.json"

# Products seen in search, keyed by our product id, so the cart can show names and limits.
_seen: dict[str, tuple[Product, int]] = {}


class ToolInfo(Model):
    name: str
    description: str
    input_schema: dict[str, Any]
    blocked: bool


class Address(Model):
    id: str
    tag: str


class BlockedToolError(RuntimeError):
    pass


class InstamartError(RuntimeError):
    pass


@asynccontextmanager
async def session() -> AsyncIterator[ClientSession]:
    headers = {"Authorization": f"Bearer {swiggy_oauth.access_token()}"}
    async with (
        httpx2.AsyncClient(headers=headers, timeout=30) as http,
        streamable_http_client(config.SWIGGY_MCP_URL, http_client=http) as (read, write),
        ClientSession(read, write) as mcp_session,
    ):
        await mcp_session.initialize()
        yield mcp_session


async def list_tools() -> list[ToolInfo]:
    async with session() as mcp_session:
        result = await mcp_session.list_tools()
    return [
        ToolInfo(
            name=tool.name,
            description=tool.description or "",
            input_schema=tool.input_schema,
            blocked=tool.name not in ALLOWED_TOOLS,
        )
        for tool in result.tools
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call an allowlisted tool; returns its structured JSON (or text if there is none)."""
    if name not in ALLOWED_TOOLS:
        raise BlockedToolError(f"'{name}' is not on the allowlist (no orders, payments or address edits)")
    async with session() as mcp_session:
        result = await mcp_session.call_tool(name, arguments)
    text = "\n".join(getattr(block, "text", "") for block in result.content)
    if result.is_error:
        raise InstamartError(f"{name} failed: {text[:300]}")
    if result.structured_content is not None:
        return result.structured_content
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# --- delivery address -------------------------------------------------------------------------


async def list_addresses() -> list[Address]:
    data = await call_tool("get_addresses", {})
    return [Address(id=a["id"], tag=a.get("addressTag") or "Saved") for a in data["addresses"]]


def selected_address() -> str | None:
    if not ADDRESS_PATH.exists():
        return None
    return Address.model_validate_json(ADDRESS_PATH.read_text()).id


def select_address(address: Address) -> None:
    ADDRESS_PATH.write_text(address.model_dump_json())


def _require_address() -> str:
    address_id = selected_address()
    if not address_id:
        raise InstamartError("choose a Swiggy delivery address first")
    return address_id


# --- InstamartClient --------------------------------------------------------------------------


class McpInstamart:
    """InstamartClient on top of Swiggy's search_products and update_cart tools."""

    async def search(self, query: str) -> list[Product]:
        data = await call_tool("search_products", {"addressId": _require_address(), "query": query})
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
            await call_tool("update_cart", {"selectedAddressId": _require_address(), "items": items})
        cart = await call_tool("get_cart", {})
        to_pay = cart.get("billBreakdown", {}).get("toPay", {}).get("value") or cart.get("cartTotalAmount")
        return CartResult(
            mode="mcp",
            items=cart_items,
            total=_rupees(to_pay, default=sum(i.line_total for i in cart_items)),
            unavailable=unavailable,
            note="Added to your Instamart cart. Review and pay in the Swiggy app.",
        )


def _rupees(value: object, default: float) -> float:
    try:
        return float(str(value).replace("₹", "").replace(",", "").strip())
    except ValueError:
        return round(default, 2)
