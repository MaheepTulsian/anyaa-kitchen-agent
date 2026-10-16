"""App config from environment variables. Values in .env win, so editing .env and saving any file
(the dev server reloads) is enough to change a setting; Docker compose loads the same file."""

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _key, _value = _line.split("=", 1)
            os.environ[_key.strip()] = _value.strip()

# Claude Agent SDK model alias (haiku | sonnet | opus); auth comes from the Claude login,
# or CLAUDE_CODE_OAUTH_TOKEN in Docker.
LLM_MODEL = os.getenv("LLM_MODEL", "haiku")  # cheapest per token

AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION", "centralindia")
AZURE_TTS_VOICE_HOUSEHOLD = os.getenv("AZURE_TTS_VOICE_HOUSEHOLD", "en-IN-NeerjaNeural")
AZURE_TTS_VOICE_COOK = os.getenv("AZURE_TTS_VOICE_COOK", "en-IN-NeerjaNeural")
# English only for now; switch to hi-IN (+ hi-IN-SwaraNeural) to bring Hindi back.
SPEECH_LANGUAGE = os.getenv("SPEECH_LANGUAGE", "en-IN")

INSTAMART_MODE = os.getenv("INSTAMART_MODE", "mock")  # mock | mcp
SWIGGY_MCP_URL = os.getenv("SWIGGY_MCP_URL", "https://mcp.swiggy.com/im")
SWIGGY_AUTH_URL = "https://mcp.swiggy.com/auth"

DB_PATH = Path(os.getenv("DB_PATH", "data/household.db"))
LOG_PATH = Path(os.getenv("LOG_PATH", "logs/events.jsonl"))

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
DATA_DIR = ROOT_DIR / "data"

# Telegram bot from @BotFather; people link their phone number by opening the bot once.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
