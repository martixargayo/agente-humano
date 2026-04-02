from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from negociacion.orchestration.context_errors import SessionContextConflictError


client = TestClient(app)


def test_negociar_returns_400_when_context_id_missing() -> None:
    response = client.post(
        "/negociar",
        json={"user_id": "u", "session_id": "s", "message": "hola"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "missing_context_id_for_stateful_negociar"


def test_negociar_returns_409_when_session_conflict(monkeypatch) -> None:
    def _raise_conflict(*args, **kwargs):
        raise SessionContextConflictError(
            session_id="s",
            existing_context_id="baseline_current",
            requested_context_id="sala_reuniones",
        )

    monkeypatch.setattr("api.app.run_legacy_negociar_turn", _raise_conflict)
    response = client.post(
        "/negociar",
        json={"user_id": "u", "session_id": "s", "message": "hola", "context_id": "sala_reuniones"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "session_context_conflict"


def test_negociar_returns_200_when_context_is_valid(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.app.run_legacy_negociar_turn",
        lambda **_: {"reply": "ok", "finish_button_armed": False, "meta": {}},
    )
    response = client.post(
        "/negociar",
        json={"user_id": "u", "session_id": "s", "message": "hola", "context_id": "baseline_current"},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Legacy-Negociar") == "deprecated_use_interfaz_usuario_or_optimizador"
    assert response.json()["reply"] == "ok"
