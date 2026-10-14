"""FastAPI dependencies: settings, a per-request DB connection, and the event log."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.events import EventLog
from app.store import connect

HOUSEHOLD_ID = 1
"""One household per DB file (see spec §2)."""


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_event_log(request: Request) -> EventLog:
    event_log: EventLog = request.app.state.event_log
    return event_log


def get_conn(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ConnDep = Annotated[sqlite3.Connection, Depends(get_conn)]
EventLogDep = Annotated[EventLog, Depends(get_event_log)]
