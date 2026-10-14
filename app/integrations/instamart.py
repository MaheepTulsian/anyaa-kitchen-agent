"""Instamart interface shared by the mock and the real Swiggy MCP client.

We only ever search and build a cart. Placing an order is never done here: the household
reviews the cart and pays in the Swiggy app.
"""

from typing import Protocol

from pydantic import Field

from app import config
from app.models import Model


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


def get_client() -> InstamartClient:
    """Real Swiggy MCP when INSTAMART_MODE=mcp and logged in; otherwise the mock."""
    from app.integrations import instamart_mcp, instamart_mock, swiggy_oauth

    if config.INSTAMART_MODE == "mcp" and swiggy_oauth.load_token() is not None:
        return instamart_mcp.McpInstamart()
    return instamart_mock.MockInstamart()
