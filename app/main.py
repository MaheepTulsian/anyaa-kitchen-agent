"""FastAPI app."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config
from app.models import StateSnapshot
from app.routes import instamart, speech
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
app.include_router(speech.router)
app.include_router(instamart.router)


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


# Static UI last so API routes win. Audio dir is created up front for generated voice notes.
(config.WEB_DIR / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")
