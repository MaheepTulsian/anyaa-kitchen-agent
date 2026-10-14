"""Typed application settings loaded from the environment (and `.env` when present)."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class InstamartMode(StrEnum):
    MOCK = "mock"
    MCP = "mcp"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-5-5"

    azure_speech_key: SecretStr | None = None
    azure_speech_region: str = "centralindia"
    azure_tts_voice_household: str = "en-IN-NeerjaNeural"
    azure_tts_voice_cook: str = "hi-IN-SwaraNeural"

    instamart_mode: InstamartMode = InstamartMode.MOCK
    swiggy_mcp_url: str = "https://mcp.swiggy.com/instamart"

    db_path: Path = Path("data/household.db")
    log_path: Path = Path("logs/events.jsonl")
    plan_window_days: int = Field(default=3, ge=1, le=7)
    timezone: str = "Asia/Kolkata"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
