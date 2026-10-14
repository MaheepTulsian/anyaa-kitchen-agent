"""What is already in the kitchen; subtracted from the grocery list."""

import sqlite3

from app.models import PantryItem


def set_pantry_item(conn: sqlite3.Connection, household_id: int, item: PantryItem) -> None:
    """Set the quantity on hand; a quantity of zero removes the item."""
    if item.qty == 0:
        conn.execute(
            "DELETE FROM pantry WHERE household_id = ? AND item = ?", (household_id, item.item)
        )
    else:
        conn.execute(
            "INSERT INTO pantry (household_id, item, qty, unit) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (household_id, item) DO UPDATE SET qty = excluded.qty, "
            "unit = excluded.unit",
            (household_id, item.item, item.qty, item.unit.value),
        )
    conn.commit()


def list_pantry(conn: sqlite3.Connection, household_id: int) -> list[PantryItem]:
    rows = conn.execute(
        "SELECT item, qty, unit FROM pantry WHERE household_id = ? ORDER BY item", (household_id,)
    ).fetchall()
    return [PantryItem.model_validate(dict(row)) for row in rows]
