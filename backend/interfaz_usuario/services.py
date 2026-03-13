from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from sessions.state import SESSIONS, SessionState, get_session_state

from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.optimizador.storage import resolve_traces


def ensure_session(*, user_id: str, session_id: str) -> dict[str, Any]:
    state = get_session_state(user_id=user_id, session_id=session_id)
    traces = resolve_traces(state)
    canonical = state.world_state.get("negotiation_canonical", {}) if isinstance(state.world_state, dict) else {}
    thread = canonical.get("openai_thread", {}) if isinstance(canonical, dict) else {}
    return {
        "user_id": user_id,
        "session_id": session_id,
        "trace_count": len(traces),
        "last_updated": state.last_updated.isoformat(),
        "conversation_id": thread.get("conversation_id") if isinstance(thread, dict) else None,
        "previous_response_id": thread.get("previous_response_id") if isinstance(thread, dict) else None,
    }


def create_new_conversation(*, user_id: str, base_session_id: str) -> dict[str, Any]:
    new_session_id = f"{base_session_id}__newconv__{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:6]}"
    SESSIONS[(user_id, new_session_id)] = SessionState(user_id=user_id, session_id=new_session_id)
    return ensure_session(user_id=user_id, session_id=new_session_id)




def _should_auto_reset_for_fresh_opener(*, state: SessionState, message: str) -> bool:
    canonical = state.world_state.get("negotiation_canonical", {}) if isinstance(state.world_state, dict) else {}
    if not isinstance(canonical, dict):
        return False
    planner_state = canonical.get("planner_state", {})
    if not isinstance(planner_state, dict):
        return False

    phase = str(planner_state.get("current_phase") or "")
    if phase not in {"formalizacion_del_acuerdo", "abandono_de_la_negociacion"}:
        return False

    raw_recent = state.world_state.get("negotiation_canonical_recent_dialogue", []) if isinstance(state.world_state, dict) else []
    recent_len = len(raw_recent) if isinstance(raw_recent, list) else 0
    if recent_len < 4:
        return False

    normalized = " ".join(message.strip().lower().split())
    fresh_openers = ("hola", "buenas", "encantado", "buenos días", "buenas tardes")
    return normalized.startswith(fresh_openers)

def run_turn(*, user_id: str, session_id: str, message: str, new_conversation: bool = False) -> dict[str, Any]:
    resolved_session_id = session_id
    auto_reset_applied = False
    if new_conversation:
        payload = create_new_conversation(user_id=user_id, base_session_id=session_id)
        resolved_session_id = payload["session_id"]
    else:
        base_state = get_session_state(user_id=user_id, session_id=session_id)
        if _should_auto_reset_for_fresh_opener(state=base_state, message=message):
            payload = create_new_conversation(user_id=user_id, base_session_id=session_id)
            resolved_session_id = payload["session_id"]
            auto_reset_applied = True

    state = get_session_state(user_id=user_id, session_id=resolved_session_id)
    config = build_negotiation_pipeline_config()
    reply, _, meta = execute_turn_with_contract(
        state=state,
        user_message=message,
        config=config,
        contract=TurnEntryContract(
            entry_surface="interfaz_usuario",
            entrypoint="/api/interfaz_usuario/negociacion/turn",
            overrides_applied=False,
            optimizer_wrapper_used=False,
            new_conversation=new_conversation,
            clone_used=False,
        ),
    )

    return {
        "reply": reply,
        "user_id": user_id,
        "session_id": resolved_session_id,
        "trace_count": meta.get("trace_count", 0),
        "conversation_id_before": meta.get("conversation_id_before"),
        "conversation_id_after": meta.get("conversation_id_after"),
        "previous_response_id_before": meta.get("previous_response_id_before"),
        "previous_response_id_after": meta.get("previous_response_id_after"),
        "latest_turn_id": meta.get("latest_turn_id"),
        "entry_contract": meta.get("entry_contract") or {},
        "auto_reset_applied": auto_reset_applied,
    }
