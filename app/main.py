"""FastAPI app."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import config
from app.models import StateSnapshot
from app.services.snapshot import build_snapshot
from app.store import connect, init_schema
from app.store.households import ensure_household


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect(config.DB_PATH)
    init_schema(conn)
    ensure_household(conn, config.HOUSEHOLD_ID)
    conn.close()
    yield


app = FastAPI(title="Anyaa Kitchen Agent", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "instamart_mode": config.INSTAMART_MODE,
        "llm_configured": bool(config.ANTHROPIC_API_KEY),
        "speech_configured": bool(config.AZURE_SPEECH_KEY),
    }


@app.get("/api/state")
def get_state() -> StateSnapshot:
    conn = connect(config.DB_PATH)
    try:
        return build_snapshot(conn, config.HOUSEHOLD_ID)
    finally:
        conn.close()
