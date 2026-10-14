from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        db_path=tmp_path / "household.db",
        log_path=tmp_path / "events.jsonl",
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_reports_unconfigured_integrations(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body == {
        "status": "ok",
        "instamart_mode": "mock",
        "llm_configured": False,
        "speech_configured": False,
    }


def test_state_of_a_fresh_household(client: TestClient) -> None:
    response = client.get("/api/state")
    assert response.status_code == 200
    body = response.json()
    assert body["phase"] == "ONBOARDING"
    assert body["members"] == []
    assert body["constraints"] == []
    assert body["cook"] is None
    assert body["plan"] is None
    assert body["instamart_mode"] == "mock"
