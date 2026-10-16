"""Observability: an append-only JSONL log where every line of one turn shares a turn id.

    turn = obs.start_turn(Agent.HOUSEHOLD, node="SETUP", text=...)   # turn_start
    turn.log("tool_call", tool=..., args=...)                         # ms since start
    turn.log("turn_end", reply=...)

Evals read latency and tool usage straight from logs/events.jsonl.
"""

import time
import uuid
from collections import deque
from typing import Any

from app import clock, config
from app.models import Agent, Event


def write(event: Event) -> None:
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json(exclude_none=True) + "\n")


def recent(limit: int = 100) -> list[Event]:
    if not config.LOG_PATH.exists():
        return []
    with config.LOG_PATH.open(encoding="utf-8") as f:
        return [Event.model_validate_json(line) for line in deque(f, maxlen=limit) if line.strip()]


class Turn:
    def __init__(self, agent: Agent) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.agent = agent
        self.started = time.monotonic()

    def log(self, kind: str, **data: Any) -> None:
        ms = int((time.monotonic() - self.started) * 1000)
        write(Event(ts=clock.real_now(), turn_id=self.id, agent=self.agent, type=kind, data=data, ms=ms))


def start_turn(agent: Agent, **data: Any) -> Turn:
    turn = Turn(agent)
    turn.log("turn_start", **data)
    return turn
