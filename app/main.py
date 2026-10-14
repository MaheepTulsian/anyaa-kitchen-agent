"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import HOUSEHOLD_ID
from app.api.routes_state import router as state_router
from app.config import Settings, get_settings
from app.events import EventLog
from app.store import connect, init_schema
from app.store.households import ensure_household


def _bootstrap_database(settings: Settings) -> None:
    conn = connect(settings.db_path)
    try:
        init_schema(conn)
        ensure_household(conn, HOUSEHOLD_ID)
    finally:
        conn.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _bootstrap_database(resolved)
        app.state.settings = resolved
        app.state.event_log = EventLog(resolved.log_path)
        yield

    app = FastAPI(title="Anyaa Kitchen Agent", version="0.1.0", lifespan=lifespan)
    app.include_router(state_router)
    return app


app = create_app()
