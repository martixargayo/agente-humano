from fastapi.testclient import TestClient

import app as app_module


def test_health_endpoint_smoke():
    app_module.openai_client = None
    app_module.speech_client = None

    with TestClient(app_module.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_negociar_endpoint_wiring_smoke(monkeypatch):
    app_module.openai_client = None
    app_module.speech_client = None

    captured = {}

    def fake_run_negotiation_agent(state, user_message):
        captured["state"] = state
        captured["user_message"] = user_message
        return "respuesta smoke", state

    monkeypatch.setattr(app_module, "run_negotiation_agent", fake_run_negotiation_agent)

    payload = {
        "user_id": "smoke-user",
        "session_id": "smoke-session",
        "message": "Hola, ¿seguimos con la oferta?",
    }

    with TestClient(app_module.app) as client:
        response = client.post("/negociar", json=payload)

    assert response.status_code == 200
    assert response.json() == {"reply": "respuesta smoke"}
    assert captured["user_message"] == payload["message"]
    assert captured["state"].user_id == payload["user_id"]
    assert captured["state"].session_id == payload["session_id"]
