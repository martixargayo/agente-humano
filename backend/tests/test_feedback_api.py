from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.app import app
from evaluacion.storage.in_memory_repository import REPOSITORY
from sessions.state import SESSIONS, get_session_state

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    SESSIONS.clear()
    REPOSITORY._jobs.clear()  # type: ignore[attr-defined]
    REPOSITORY._reports.clear()  # type: ignore[attr-defined]


def _seed_dialogue(*, user_id: str, session_id: str, turns: int = 2) -> None:
    state = get_session_state(user_id=user_id, session_id=session_id)
    history = []
    for idx in range(1, turns + 1):
        history.append({"role": "user", "content": f"Turno usuario {idx}: ¿Podemos ajustar precio?"})
        history.append({"role": "assistant", "content": f"Turno asistente {idx}: Revisemos condiciones."})
    state.history = history


def _wait_until_terminal(evaluation_id: str, timeout_s: float = 2.5) -> dict:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_s:
        status = client.get(f"/api/interfaz_usuario/feedback/evaluations/{evaluation_id}")
        assert status.status_code == 200
        payload = status.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.02)
    raise AssertionError("evaluation did not reach terminal status in time")


def test_create_evaluation_is_async_and_not_inline_completed() -> None:
    _seed_dialogue(user_id="u_fb", session_id="s_fb", turns=3)

    res = client.post(
        "/api/interfaz_usuario/feedback/evaluations",
        json={"user_id": "u_fb", "session_id": "s_fb"},
    )
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["evaluation_id"], str)
    assert body["status"] in {"created", "queued", "building_inputs", "running_core", "running_trajectory", "assembling_report"}


def test_get_report_before_completed_returns_409() -> None:
    _seed_dialogue(user_id="u_fb2", session_id="s_fb2", turns=2)
    created = client.post(
        "/api/interfaz_usuario/feedback/evaluations",
        json={"user_id": "u_fb2", "session_id": "s_fb2"},
    )
    evaluation_id = created.json()["evaluation_id"]

    early = client.get(f"/api/interfaz_usuario/feedback/evaluations/{evaluation_id}/report")
    assert early.status_code in {409, 200}


def test_status_and_report_terminal_success() -> None:
    _seed_dialogue(user_id="u_fb3", session_id="s_fb3", turns=4)
    created = client.post(
        "/api/interfaz_usuario/feedback/evaluations",
        json={"user_id": "u_fb3", "session_id": "s_fb3"},
    )
    evaluation_id = created.json()["evaluation_id"]

    terminal = _wait_until_terminal(evaluation_id)
    assert terminal["status"] == "completed"
    assert isinstance(terminal["stage_latencies_ms"], dict)

    report = client.get(f"/api/interfaz_usuario/feedback/evaluations/{evaluation_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert body["report"]["schema_version"] == "ui_feedback_report.v1"
    assert len(body["report"]["block_cards"]) == 4
    assert "key_moments" in body["report"]
    assert "recommendations" in body["report"]
    assert body["report"]["provenance"]["core_model"] == "gpt-5.4"


def test_nonexistent_session_is_handled_and_completes_with_conservative_report() -> None:
    created = client.post(
        "/api/interfaz_usuario/feedback/evaluations",
        json={"user_id": "u_missing", "session_id": "s_missing"},
    )
    evaluation_id = created.json()["evaluation_id"]

    terminal = _wait_until_terminal(evaluation_id)
    assert terminal["status"] == "completed"
    report = client.get(f"/api/interfaz_usuario/feedback/evaluations/{evaluation_id}/report")
    assert report.status_code == 200


def test_get_status_not_found() -> None:
    res = client.get("/api/interfaz_usuario/feedback/evaluations/not-found")
    assert res.status_code == 404
