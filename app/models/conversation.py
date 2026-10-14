"""Conversation turns and structured log events."""

import datetime as dt
from typing import Any

from pydantic import Field

from app.models.base import Model
from app.models.enums import Agent, EventType, Phase, Role


class Message(Model):
    id: int | None = None
    agent: Agent
    role: Role
    content: str
    created_at: dt.datetime


class Event(Model):
    """One line in `logs/events.jsonl`."""

    ts: dt.datetime
    household_id: int
    turn_id: str | None = None
    agent: Agent | None = None
    phase: Phase | None = None
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = Field(default=None, ge=0)
