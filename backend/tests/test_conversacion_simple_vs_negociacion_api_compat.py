from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import app
from sessions.state import get_session_store


def _mock_neg_turn(*, state, user_message, config, contract, turn_context):
    return "neg-reply", state, {
        "trace_count": 1,
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


def _mock_cs_turn(*, state, user_message, config, turn_context, **kwargs):
    state.world_state.setdefault(config.memory_key, {"ui_state": {"finish_button_armed": True}})
    state.world_state[config.memory_key].setdefault("ui_state", {})["finish_button_armed"] = True
    state.world_state.setdefault(config.traces_key, []).append(
        {
            "turn_id": "cs-turn",
            "pipeline_topology": "single_llm",
            "nodes": {"brain": {"node_name": "brain", "status": "deliver", "model_called": True, "latency_ms": 1}},
            "memory_observability": {},
            "final_reply_text": "cs-reply",
            "final_status": "deliver",
        }
    )
    return "cs-reply", state, {"turn_id": "cs-turn", "pipeline_topology": "single_llm", "node_names": ["brain"]}


def test_bootstrap_finalize_turn_parity_envelope(monkeypatch) -> None:
    get_session_store().clear()
    monkeypatch.setattr("interfaz_usuario.services.execute_turn_with_contract", _mock_neg_turn)
    monkeypatch.setattr("interfaz_usuario.services.run_conversacion_simple_turn", _mock_cs_turn)

    client = TestClient(app)

    boot_neg = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u1", "session_id": "s1", "context_id": "baseline_current"})
    boot_cs = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u2", "session_id": "s2", "context_id": "baseline"})
    assert boot_neg.status_code == 200
    assert boot_cs.status_code == 200

    turn_neg = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u1", "session_id": "s1", "message": "hola"})
    turn_cs = client.post("/api/interfaz_usuario/negociacion/turn", json={"user_id": "u2", "session_id": "s2", "message": "hola"})
    assert turn_neg.status_code == 200
    assert turn_cs.status_code == 200

    finalize_neg = client.post("/api/interfaz_usuario/sessions/finalize", json={"user_id": "u1", "session_id": "s1"})
    finalize_cs = client.post("/api/interfaz_usuario/sessions/finalize", json={"user_id": "u2", "session_id": "s2"})
    assert finalize_neg.status_code == 200
    assert finalize_cs.status_code == 200

    neg_turn_keys = set(turn_neg.json().keys())
    cs_turn_keys = set(turn_cs.json().keys())
    required_external = {"reply", "user_id", "session_id", "trace_count", "entry_contract", "latest_turn_id", "finish_button_armed"}
    assert required_external.issubset(neg_turn_keys)
    assert required_external.issubset(cs_turn_keys)
    assert turn_cs.json()["finish_button_armed"] is True


def test_context_conflict_parity_between_flows(monkeypatch) -> None:
    get_session_store().clear()
    monkeypatch.setattr("interfaz_usuario.services.execute_turn_with_contract", _mock_neg_turn)
    monkeypatch.setattr("interfaz_usuario.services.run_conversacion_simple_turn", _mock_cs_turn)
    client = TestClient(app)

    ok = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u3", "session_id": "s3", "context_id": "baseline"})
    assert ok.status_code == 200
    conflict = client.post("/api/interfaz_usuario/sessions/bootstrap", json={"user_id": "u3", "session_id": "s3", "context_id": "baseline_current"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "session_context_conflict"
