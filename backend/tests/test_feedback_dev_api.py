from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.app import app
from evaluacion.storage.in_memory_repository import REPOSITORY
from sessions.state import SESSIONS

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    SESSIONS.clear()
    REPOSITORY._jobs.clear()  # type: ignore[attr-defined]
    REPOSITORY._reports.clear()  # type: ignore[attr-defined]
    monkeypatch.delenv("ENABLE_FEEDBACK_DEV_FIXTURES", raising=False)


def _wait_terminal(evaluation_id: str, timeout_s: float = 3.5) -> dict:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_s:
        status = client.get(f"/api/interfaz_usuario/feedback/evaluations/{evaluation_id}")
        if status.status_code != 200:
            raise AssertionError(status.text)
        payload = status.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.03)
    raise AssertionError("demo evaluation did not reach terminal state")


def test_dev_fixtures_disabled_returns_404() -> None:
    r = client.get("/api/interfaz_usuario/feedback/dev/fixtures")
    assert r.status_code == 404


def test_list_dev_fixtures_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_FEEDBACK_DEV_FIXTURES", "1")
    r = client.get("/api/interfaz_usuario/feedback/dev/fixtures")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["fixtures"], list)
    assert any(f["fixture_id"] == "negotiation_demo_01" for f in body["fixtures"])


def test_create_demo_evaluation_by_fixture_id_and_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_FEEDBACK_DEV_FIXTURES", "1")

    created = client.post(
        "/api/interfaz_usuario/feedback/dev/evaluations",
        json={"fixture_id": "negotiation_demo_01"},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["fixture_id"] == "negotiation_demo_01"
    assert isinstance(payload["evaluation_id"], str)

    terminal = _wait_terminal(payload["evaluation_id"])
    assert terminal["status"] == "completed"

    report = client.get(f"/api/interfaz_usuario/feedback/evaluations/{payload['evaluation_id']}/report")
    assert report.status_code == 200
    report_body = report.json()
    assert report_body["report"]["schema_version"] == "ui_feedback_report.v1"


def test_create_demo_evaluation_invalid_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_FEEDBACK_DEV_FIXTURES", "1")
    created = client.post(
        "/api/interfaz_usuario/feedback/dev/evaluations",
        json={"fixture_id": "missing_fixture"},
    )
    assert created.status_code == 404
