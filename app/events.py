"""Append-only JSONL event log. Evals read latency and tool usage from this file."""

import threading
from collections import deque
from pathlib import Path

from app.models import Event

_REDACTED_KEYS = frozenset({"api_key", "authorization", "token", "subscription_key"})


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in _REDACTED_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class EventLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: Event) -> None:
        safe = event.model_copy(update={"data": _redact(event.data)})
        line = safe.model_dump_json(exclude_none=True)
        with self._lock, self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def tail(self, limit: int = 100) -> list[Event]:
        if not self._path.exists():
            return []
        with self._lock, self._path.open(encoding="utf-8") as handle:
            lines = deque(handle, maxlen=limit)
        return [Event.model_validate_json(line) for line in lines if line.strip()]
