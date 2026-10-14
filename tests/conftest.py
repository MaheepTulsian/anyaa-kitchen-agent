import sqlite3
from collections.abc import Iterator

import pytest

from app.store import connect, init_schema
from app.store.households import ensure_household

HOUSEHOLD_ID = 1


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    connection = connect(":memory:")
    init_schema(connection)
    ensure_household(connection, HOUSEHOLD_ID)
    yield connection
    connection.close()
