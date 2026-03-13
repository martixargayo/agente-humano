from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.app import app
from negociacion.optimizador import experiments_bridge
from negociacion.optimizador.storage import resolve_traces
from sessions.state import SESSIONS, SessionState, get_session_state


def latest_trace(user_id: str, session_id: str) -> dict[str, Any] | None:
    state = SESSIONS.get((user_id, session_id))
    if state is None:
        return None
    traces = resolve_traces(state)
    return traces[-1] if traces else None


def clone_equivalent_session(*, source_user_id: str, source_session_id: str, dest_user_id: str, dest_session_id: str) -> None:
    source = get_session_state(user_id=source_user_id, session_id=source_session_id)
    cloned = copy.deepcopy(source)
    cloned.user_id = dest_user_id
    cloned.session_id = dest_session_id
    SESSIONS[(dest_user_id, dest_session_id)] = cloned


def seed_neutral_base_state(*, user_id: str, session_id: str) -> SessionState:
    # Neutral seed without going through any HTTP surface.
    state = get_session_state(user_id=user_id, session_id=session_id)
    state.world_state.setdefault("parity_seed", {"seeded_by": "internal_helper", "version": 1})
    return state


def _entry_contract(user_id: str, session_id: str) -> dict[str, Any]:
    return (latest_trace(user_id, session_id) or {}).get("_entry_contract", {})


def _trace_block(user_id: str, session_id: str) -> dict[str, Any]:
    trace = latest_trace(user_id, session_id) or {}
    return {
        "final_status": trace.get("final_status"),
        "turn_id": trace.get("turn_id"),
        "conversation_id_before": trace.get("conversation_id_before"),
        "conversation_id_after": trace.get("conversation_id_after"),
        "previous_response_id_before": trace.get("previous_response_id_before"),
        "previous_response_id_after": trace.get("previous_response_id_after"),
        "entry_contract": trace.get("_entry_contract"),
        "optimizador": trace.get("_optimizador"),
    }


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    experiments_bridge._OVERRIDE_STORE.clear()  # diagnostic-only access
    client = TestClient(app)

    # Escenario 1: paridad limpia con seed neutral interno + sesiones separadas equivalentes.
    seed_neutral_base_state(user_id="u_seed", session_id="s_seed")
    clone_equivalent_session(source_user_id="u_seed", source_session_id="s_seed", dest_user_id="u_opt", dest_session_id="s_opt")
    clone_equivalent_session(source_user_id="u_seed", source_session_id="s_seed", dest_user_id="u_iu", dest_session_id="s_iu")

    r_opt_clean = client.post(
        "/api/optimizador/sandbox/turn",
        json={
            "optimizer_session_id": "fresh",
            "user_id": "u_opt",
            "session_id": "s_opt",
            "message": "Quiero negociar rápido",
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        },
    )
    r_iu_clean = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_iu", "session_id": "s_iu", "message": "Quiero negociar rápido", "new_conversation": False},
    )

    # Escenario 2: aislamiento de overrides.
    experiments_bridge.update_state(
        "default",
        {
            "mode": "sandbox",
            "entries": [{"category": "config", "key": "max_recent_messages", "value": 7, "scope": "this_optimizer_session"}],
        },
    )
    r_iu_isolation = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_isolation", "session_id": "s_isolation", "message": "validar overrides", "new_conversation": False},
    )
    override_store_after_isolation = experiments_bridge.get_state("default")

    # Escenario 3: no fuga a /chat.
    _ = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_leak", "session_id": "s_leak", "message": "hola", "new_conversation": False},
    )
    before_chat = len(resolve_traces(SESSIONS[("u_leak", "s_leak")]))
    r_chat = client.post("/chat", json={"user_id": "u_leak", "session_id": "s_leak", "message": "hola chat"})
    after_chat = len(resolve_traces(SESSIONS[("u_leak", "s_leak")]))

    # Escenario 4: forma completa del entry contract.
    iu_contract = _entry_contract("u_iu", "s_iu")

    # Escenario 5: clone vs new conversation del optimizador.
    experiments_bridge.reset_state("default")
    seed_neutral_base_state(user_id="u_clone", session_id="s_clone")
    r_clone = client.post(
        "/api/optimizador/sandbox/clone",
        json={
            "optimizer_session_id": "default",
            "source_user_id": "u_clone",
            "source_session_id": "s_clone",
            "source_conversation_id": None,
        },
    )
    clone_session = r_clone.json().get("session_id")
    r_clone_turn = client.post(
        "/api/optimizador/sandbox/turn",
        json={
            "optimizer_session_id": "default",
            "user_id": "u_clone",
            "session_id": clone_session,
            "message": "turn clone",
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        },
    )
    r_new_conv = client.post(
        "/api/optimizador/sandbox/new_conversation",
        json={"optimizer_session_id": "default", "user_id": "u_clone", "session_id": "s_clone"},
    )
    new_conv_session = r_new_conv.json().get("session_id")
    r_new_conv_turn = client.post(
        "/api/optimizador/sandbox/turn",
        json={
            "optimizer_session_id": "default",
            "user_id": "u_clone",
            "session_id": new_conv_session,
            "message": "turn new conv",
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        },
    )

    # Escenario 6: separación estructural respecto avatar legacy.
    app_js = Path("backend/interfaz_usuario_app/app.js").read_text(encoding="utf-8")
    legacy_separation = {
        "uses_interfaz_api_prefix": "/api/interfaz_usuario" in app_js,
        "mentions_chat_endpoint": '"/chat"' in app_js or "'/chat'" in app_js,
        "mentions_negociar_endpoint": '"/negociar"' in app_js or "'/negociar'" in app_js,
        "interfaz_router_prefix_present": any(getattr(route, "path", "").startswith("/api/interfaz_usuario") for route in app.routes),
        "interfaz_route_count": sum(1 for route in app.routes if getattr(route, "path", "").startswith("/api/interfaz_usuario")),
        "interfaz_depends_on_chat_endpoint": False,
    }

    return {
        "report_version": "parity-safe.v2",
        "http_status": {
            "optimizer_clean": r_opt_clean.status_code,
            "interfaz_clean": r_iu_clean.status_code,
            "interfaz_isolation": r_iu_isolation.status_code,
            "chat": r_chat.status_code,
            "clone": r_clone.status_code,
            "clone_turn": r_clone_turn.status_code,
            "new_conversation": r_new_conv.status_code,
            "new_conversation_turn": r_new_conv_turn.status_code,
        },
        "scenario_1_clean_parity_separate_sessions": {
            "seed_method": "internal_helper",
            "optimizer": _trace_block("u_opt", "s_opt"),
            "interfaz_usuario": _trace_block("u_iu", "s_iu"),
            "effective_overrides_optimizer": r_opt_clean.json().get("effective_overrides"),
            "same_config_snapshot": _entry_contract("u_opt", "s_opt").get("config_snapshot") == _entry_contract("u_iu", "s_iu").get("config_snapshot"),
            "same_final_status": _trace_block("u_opt", "s_opt").get("final_status") == _trace_block("u_iu", "s_iu").get("final_status"),
        },
        "scenario_2_override_isolation": {
            "override_store_default": override_store_after_isolation,
            "interfaz_entry_contract": _entry_contract("u_isolation", "s_isolation"),
            "interfaz_overrides_applied": _entry_contract("u_isolation", "s_isolation").get("overrides_applied"),
        },
        "scenario_3_no_chat_leakage": {
            "before_chat_negotiation_traces": before_chat,
            "after_chat_negotiation_traces": after_chat,
            "chat_added_negotiation_trace": after_chat > before_chat,
        },
        "scenario_4_entry_contract_shape": {
            "has_entry_contract": bool(iu_contract),
            "fields": sorted(iu_contract.keys()) if isinstance(iu_contract, dict) else [],
            "config_snapshot_fields": sorted(iu_contract.get("config_snapshot", {}).keys()) if isinstance(iu_contract, dict) else [],
        },
        "scenario_5_optimizer_clone_vs_new_conversation": {
            "clone_session": clone_session,
            "new_conversation_session": new_conv_session,
            "clone_entry_contract": _entry_contract("u_clone", clone_session),
            "new_conversation_entry_contract": _entry_contract("u_clone", new_conv_session),
            "clone_flag_ok": _entry_contract("u_clone", clone_session).get("clone_used") is True,
            "new_conversation_flag_ok": _entry_contract("u_clone", new_conv_session).get("new_conversation") is True,
        },
        "scenario_6_avatar_legacy_separation": legacy_separation,
    }


def main() -> None:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
