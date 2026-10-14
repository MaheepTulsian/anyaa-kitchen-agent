"""Append-only JSONL event log. Evals read latency and tool usage from this file."""

from collections import deque

from app.config import LOG_PATH
from app.models import Event


def log_event(event: Event) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json(exclude_none=True) + "\n")


def recent_events(limit: int = 100) -> list[Event]:
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open(encoding="utf-8") as f:
        lines = deque(f, maxlen=limit)
    return [Event.model_validate_json(line) for line in lines if line.strip()]
