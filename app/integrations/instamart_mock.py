"""Deterministic Instamart stand-in backed by data/mock_instamart.json."""

import json

from app import config
from app.integrations.instamart import CartItem, CartLine, CartResult, Product

CATALOG_PATH = config.DATA_DIR / "mock_instamart.json"


def _load() -> list[dict]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


class MockInstamart:
    def __init__(self) -> None:
        self.rows = _load()
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


def _product_fields(row: dict) -> dict:
    return {key: row[key] for key in ("id", "name", "brand", "pack", "price", "in_stock") if key in row}
