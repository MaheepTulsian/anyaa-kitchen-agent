from pathlib import Path

from app import clock
from app.events import EventLog
from app.models import Event, EventType


def _event(data: dict[str, object]) -> Event:
    return Event(ts=clock.real_now(), household_id=1, type=EventType.TOOL_CALL, data=data)


def test_events_round_trip_in_order(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "logs" / "events.jsonl")
    for index in range(5):
        log.write(_event({"n": index}))
    tail = log.tail(limit=3)
    assert [event.data["n"] for event in tail] == [2, 3, 4]


def test_secrets_are_redacted_at_any_depth(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.write(_event({"headers": {"Authorization": "Bearer abc"}, "api_key": "sk-123"}))
    raw = path.read_text()
    assert "abc" not in raw
    assert "sk-123" not in raw


def test_tail_of_missing_file_is_empty(tmp_path: Path) -> None:
    assert EventLog(tmp_path / "none.jsonl").tail() == []
