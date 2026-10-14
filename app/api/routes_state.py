"""Read-only routes: health and the UI state snapshot."""

from fastapi import APIRouter

from app.api.deps import HOUSEHOLD_ID, ConnDep, SettingsDep
from app.models import Model, StateSnapshot
from app.services.snapshot import build_snapshot

router = APIRouter()


class Health(Model):
    status: str
    instamart_mode: str
    llm_configured: bool
    speech_configured: bool


@router.get("/health")
def health(settings: SettingsDep) -> Health:
    return Health(
        status="ok",
        instamart_mode=settings.instamart_mode.value,
        llm_configured=settings.anthropic_api_key is not None,
        speech_configured=settings.azure_speech_key is not None,
    )


@router.get("/api/state")
def get_state(conn: ConnDep, settings: SettingsDep) -> StateSnapshot:
    return build_snapshot(conn, HOUSEHOLD_ID, settings)
