from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from api.app import app
from negociacion.optimizador import experiments_bridge
from negociacion.optimizador.storage import resolve_traces
from sessions.state import SESSIONS, SessionState, get_session_state

REPORT_PATH = Path("backend/docs/forensics_optimizer_vs_interfaz_usuario_run.json")


def _clone_state(*, source_user_id: str, source_session_id: str, dest_user_id: str, dest_session_id: str) -> None:
    source = get_session_state(user_id=source_user_id, session_id=source_session_id)
    cloned = copy.deepcopy(source)
    cloned.user_id = dest_user_id
    cloned.session_id = dest_session_id
    SESSIONS[(dest_user_id, dest_session_id)] = cloned


def _stubbed_runtime(state: SessionState, user_message: str, config: Any) -> tuple[str, SessionState]:
    memory_key = config.memory_key
    traces_key = f"{memory_key}_traces"
    traces = state.world_state.setdefault(traces_key, [])
    if not isinstance(traces, list):
        traces = []
        state.world_state[traces_key] = traces

    canonical = state.world_state.setdefault(memory_key, {})
    if not isinstance(canonical, dict):
        canonical = {}
        state.world_state[memory_key] = canonical
    thread = canonical.setdefault("openai_thread", {})
    if not isinstance(thread, dict):
        thread = {}
        canonical["openai_thread"] = thread

    idx = len(traces) + 1
    before_conv = thread.get("conversation_id")
    before_prev = thread.get("previous_response_id")
    after_conv = before_conv or f"conv::{state.user_id}::{state.session_id}"
    after_prev = f"resp::{state.session_id}::{idx}"

    recent_dialogue = state.world_state.get(f"{memory_key}_recent_dialogue", [])
    trace = {
        "turn_id": f"turn::{idx}",
        "final_status": "ok",
        "final_reply_text": f"stub::{user_message}",
        "conversation_id_before": before_conv,
        "conversation_id_after": after_conv,
        "previous_response_id_before": before_prev,
        "previous_response_id_after": after_prev,
        "forensics_payload": {
            "memory_key": memory_key,
            "thread_mode_default": config.thread_mode_default.value,
            "max_recent_messages": config.max_recent_messages,
            "max_executor_recent_turns": config.max_executor_recent_turns,
            "model_memory": config.model_memory,
            "model_phase_classifier": config.model_phase_classifier,
            "model_planner": config.model_planner,
            "model_executor": config.model_executor,
            "world_state_keys": sorted(state.world_state.keys()),
            "has_optimizer_meta": isinstance(state.world_state.get("optimizador_sandbox_meta"), dict),
            "recent_dialogue_count": len(recent_dialogue) if isinstance(recent_dialogue, list) else 0,
        },
    }
    traces.append(trace)
    thread["conversation_id"] = after_conv
    thread["previous_response_id"] = after_prev

    return f"stub::{user_message}", state


def _latest_trace(user_id: str, session_id: str) -> dict[str, Any]:
    state = get_session_state(user_id=user_id, session_id=session_id)
    traces = resolve_traces(state)
    return traces[-1] if traces else {}


def _turn_block(user_id: str, session_id: str) -> dict[str, Any]:
    latest = _latest_trace(user_id, session_id)
    return {
        "turn_id": latest.get("turn_id"),
        "final_status": latest.get("final_status"),
        "conversation_id_before": latest.get("conversation_id_before"),
        "conversation_id_after": latest.get("conversation_id_after"),
        "previous_response_id_before": latest.get("previous_response_id_before"),
        "previous_response_id_after": latest.get("previous_response_id_after"),
        "entry_contract": latest.get("_entry_contract"),
        "optimizador": latest.get("_optimizador"),
        "forensics_payload": latest.get("forensics_payload"),
    }


def build_report() -> dict[str, Any]:
    SESSIONS.clear()
    experiments_bridge._OVERRIDE_STORE.clear()  # diagnostic scope only
    client = TestClient(app)

    with patch("negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn", _stubbed_runtime):
        # Scenario 1: same seed, separate sessions, same message.
        _ = get_session_state(user_id="seed_u", session_id="seed_s")
        _clone_state(source_user_id="seed_u", source_session_id="seed_s", dest_user_id="opt_u", dest_session_id="opt_s")
        _clone_state(source_user_id="seed_u", source_session_id="seed_s", dest_user_id="iu_u", dest_session_id="iu_s")

        r_opt = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": "forensics",
                "user_id": "opt_u",
                "session_id": "opt_s",
                "message": "mensaje controlado",
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            },
        )
        r_iu = client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={"user_id": "iu_u", "session_id": "iu_s", "message": "mensaje controlado", "new_conversation": False},
        )

        s1_opt_block = _turn_block("opt_u", "opt_s")
        s1_iu_block = _turn_block("iu_u", "iu_s")

        # Scenario 2: continuity turn 2 on both surfaces.
        r_opt_2 = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": "forensics",
                "user_id": "opt_u",
                "session_id": "opt_s",
                "message": "segundo turno",
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            },
        )
        r_iu_2 = client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={"user_id": "iu_u", "session_id": "iu_s", "message": "segundo turno", "new_conversation": False},
        )
        s2_opt_latest = _latest_trace("opt_u", "opt_s")
        s2_iu_latest = _latest_trace("iu_u", "iu_s")

        # Scenario 3: optimizer override impact vs interfaz isolation.
        experiments_bridge.update_state(
            "forensics",
            {
                "mode": "sandbox",
                "entries": [
                    {"category": "config", "key": "max_recent_messages", "value": 7, "scope": "this_optimizer_session"},
                    {"category": "config", "key": "max_executor_recent_turns", "value": 2, "scope": "this_optimizer_session"},
                ],
            },
        )
        r_opt_override = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": "forensics",
                "user_id": "opt_u",
                "session_id": "opt_s",
                "message": "turno con override",
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            },
        )
        r_iu_isolated = client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={"user_id": "iu_u", "session_id": "iu_s", "message": "turno aislado", "new_conversation": False},
        )
        s3_opt_block = _turn_block("opt_u", "opt_s")
        s3_iu_block = _turn_block("iu_u", "iu_s")

        # Scenario 4: clone vs new conversation flags in optimizer.
        base_user, base_session = "clone_u", "clone_base"
        _ = get_session_state(user_id=base_user, session_id=base_session)
        clone_resp = client.post(
            "/api/optimizador/sandbox/clone",
            json={
                "optimizer_session_id": "forensics",
                "source_user_id": base_user,
                "source_session_id": base_session,
                "source_conversation_id": None,
            },
        )
        clone_session = clone_resp.json().get("session_id")
        clone_turn = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": "forensics",
                "user_id": base_user,
                "session_id": clone_session,
                "message": "turno clone",
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            },
        )
        newconv_resp = client.post(
            "/api/optimizador/sandbox/new_conversation",
            json={"optimizer_session_id": "forensics", "user_id": base_user, "session_id": base_session},
        )
        newconv_session = newconv_resp.json().get("session_id")
        newconv_turn = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": "forensics",
                "user_id": base_user,
                "session_id": newconv_session,
                "message": "turno newconv",
                "conversation_id": None,
                "scope_turn_id": None,
                "repeat_from_turn_id": None,
            },
        )
        s4_clone_block = _turn_block(base_user, clone_session)
        s4_newconv_block = _turn_block(base_user, newconv_session)

        # Scenario 5: interfaz new_conversation semantics.
        iu_newconv = client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={"user_id": "iu_new", "session_id": "iu_main", "message": "inicio", "new_conversation": True},
        )

        # Scenario 6: /chat does not append negotiation traces.
        client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={"user_id": "leak_u", "session_id": "leak_s", "message": "hola", "new_conversation": False},
        )
        before_chat = len(resolve_traces(get_session_state(user_id="leak_u", session_id="leak_s")))
        chat_resp = client.post("/chat", json={"user_id": "leak_u", "session_id": "leak_s", "message": "legacy"})
        after_chat = len(resolve_traces(get_session_state(user_id="leak_u", session_id="leak_s")))
        # Scenario 7: sticky-state boundary opener auto-reset in interfaz_usuario.
        sticky = get_session_state(user_id="iu_sticky", session_id="s_sticky")
        sticky.world_state["negotiation_canonical"] = {
            "planner_state": {"current_phase": "presentacion", "current_turn_goal": "cerrar precio final"},
            "openai_thread": {"previous_response_id": "resp_old"},
        }
        sticky.world_state["negotiation_canonical_recent_dialogue"] = [
            {"role": "user", "text": "vamos"},
            {"role": "assistant", "text": "seguimos"},
        ]
        iu_boundary = client.post(
            "/api/interfaz_usuario/negociacion/turn",
            json={"user_id": "iu_sticky", "session_id": "s_sticky", "message": "empecemos de cero", "new_conversation": False},
        )

    report = {
        "report_version": "forensics.v1",
        "status_codes": {
            "optimizer_turn_1": r_opt.status_code,
            "interfaz_turn_1": r_iu.status_code,
            "optimizer_turn_2": r_opt_2.status_code,
            "interfaz_turn_2": r_iu_2.status_code,
            "optimizer_override": r_opt_override.status_code,
            "interfaz_isolated": r_iu_isolated.status_code,
            "optimizer_clone": clone_resp.status_code,
            "optimizer_clone_turn": clone_turn.status_code,
            "optimizer_newconv": newconv_resp.status_code,
            "optimizer_newconv_turn": newconv_turn.status_code,
            "interfaz_newconv": iu_newconv.status_code,
            "chat": chat_resp.status_code,
        },
        "scenario_1_same_seed_same_message": {
            "optimizer": s1_opt_block,
            "interfaz": s1_iu_block,
            "same_config_snapshot": s1_opt_block.get("entry_contract", {}).get("config_snapshot")
            == s1_iu_block.get("entry_contract", {}).get("config_snapshot"),
            "overrides_applied_optimizer": s1_opt_block.get("entry_contract", {}).get("overrides_applied"),
            "overrides_applied_interfaz": s1_iu_block.get("entry_contract", {}).get("overrides_applied"),
        },
        "scenario_2_continuity_second_turn": {
            "optimizer_second_turn": s2_opt_latest,
            "interfaz_second_turn": s2_iu_latest,
        },
        "scenario_3_override_vs_isolation": {
            "optimizer_after_override": s3_opt_block,
            "interfaz_after_override": s3_iu_block,
            "optimizer_effective_overrides": r_opt_override.json().get("effective_overrides"),
            "override_store": experiments_bridge.get_state("forensics"),
        },
        "scenario_4_optimizer_clone_vs_newconv": {
            "clone_session_id": clone_session,
            "clone_trace": s4_clone_block,
            "newconv_session_id": newconv_session,
            "newconv_trace": s4_newconv_block,
        },
        "scenario_5_interfaz_new_conversation": iu_newconv.json(),
        "scenario_6_no_chat_trace_leak": {
            "before_chat": before_chat,
            "after_chat": after_chat,
            "chat_added_negotiation_trace": after_chat > before_chat,
        },
        "scenario_7_interfaz_boundary_auto_reset": iu_boundary.json(),
    }
    return report


def main() -> None:
    report = build_report()
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
