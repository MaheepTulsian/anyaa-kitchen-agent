"""SQLite persistence. Each submodule owns one aggregate; all functions take an open connection."""

from app.store.db import connect, init_schema, transaction

__all__ = ["connect", "init_schema", "transaction"]
