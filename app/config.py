"""App config from environment variables (docker compose loads them from .env)."""

import os
from pathlib import Path

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "centralindia")
AZURE_TTS_VOICE_HOUSEHOLD = os.getenv("AZURE_TTS_VOICE_HOUSEHOLD", "en-IN-NeerjaNeural")
AZURE_TTS_VOICE_COOK = os.getenv("AZURE_TTS_VOICE_COOK", "en-IN-NeerjaNeural")
# English only for now; switch to hi-IN (+ hi-IN-SwaraNeural) to bring Hindi back.
SPEECH_LANGUAGE = os.getenv("SPEECH_LANGUAGE", "en-IN")

INSTAMART_MODE = os.getenv("INSTAMART_MODE", "mock")  # mock | mcp
SWIGGY_MCP_URL = os.getenv("SWIGGY_MCP_URL", "https://mcp.swiggy.com/instamart")

DB_PATH = Path(os.getenv("DB_PATH", "data/household.db"))
LOG_PATH = Path(os.getenv("LOG_PATH", "logs/events.jsonl"))
PLAN_WINDOW_DAYS = int(os.getenv("PLAN_WINDOW_DAYS", "3"))

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

HOUSEHOLD_ID = 1  # one household per DB file
