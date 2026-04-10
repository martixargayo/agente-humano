from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from sessions.state import get_session_store


def _fake_neg(*, state, user_message, config, contract, turn_context):
    return "neg", state, {
        "trace_count": state.turn_count,
        "latest_turn_id": "neg-turn",
        "entry_contract": {
            "entry_surface": "interfaz_usuario",
            "entrypoint": "/api/interfaz_usuario/negociacion/turn",
            "overrides_applied": False,
            "optimizer_wrapper_used": False,
            "new_conversation": False,
            "clone_used": False,
            "config_snapshot": {
                "memory_key": "negotiation_canonical",
                "thread_mode_default": "conversation",
                "model_memory": "m",
                "model_phase_classifier": "m",
                "model_planner": "m",
                "model_executor": "m",
                "max_recent_messages": 12,
                "max_executor_recent_turns": 8,
            },
        },
    }


def _fake_cs(*, state, user_message, config, turn_context, **kwargs):
    return "cs", state, {"turn_id": "cs-turn", "pipeline_topology": "single_llm", "node_names": ["brain"]}


def test_multi_turn_stability_and_mixed_flow_boundaries(monkeypatch) -> None:
    get_session_store().clear()
    monkeypatch.setattr("interfaz_usuario.services.execute_turn_with_contract", _fake_neg)
    monkeypatch.setattr("interfaz_usuario.services.run_conversacion_simple_turn", _fake_cs)

    client = TestClient(app)

    boot_neg = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u_neg", "session_id": "s_neg", "context_id": "baseline_current"})
    boot_cs = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u_cs", "session_id": "s_cs", "context_id": "baseline"})
    assert boot_neg.status_code == 200
    assert boot_cs.status_code == 200

    for _ in range(8):
        r1 = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_neg", "session_id": "s_neg", "message": "hola"})
        r2 = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u_cs", "session_id": "s_cs", "message": "hola"})
        assert r1.status_code == 200
        assert r2.status_code == 200

    mixed_conflict = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u_cs", "session_id": "s_cs", "context_id": "baseline_current"})
    assert mixed_conflict.status_code == 409
