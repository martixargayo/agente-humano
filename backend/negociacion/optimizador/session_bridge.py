from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sessions.state import get_session_store

from . import context_bridge, storage


def list_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for user_id, session_id, state in storage.iter_optimizer_session_entries():
        traces = storage.resolve_traces(state)
        meta = state.world_state.get("optimizador_sandbox_meta", {}) if isinstance(state.world_state, dict) else {}
        context = context_bridge.ensure_optimizer_session_context(state=state)
        sessions.append(
            {
                "session_key": storage.session_key(user_id, session_id),
                "user_id": user_id,
                "session_id": session_id,
                "turn_count": len(traces),
                "last_updated": state.last_updated.isoformat(),
                "is_sandbox": bool(meta),
                "sandbox_meta": meta if isinstance(meta, dict) else {},
                "base_context": context,
            }
        )
    sessions.sort(key=lambda item: item["last_updated"], reverse=True)
    return sessions


def list_conversations(user_id: str, session_id: str) -> list[dict[str, Any]]:
    state = storage.get_optimizer_state(user_id, session_id)
    if state is None:
        return []
    grouped: dict[str, int] = defaultdict(int)
    for turn in storage.resolve_traces(state):
        conversation_id = turn.get("conversation_id_after") or turn.get("conversation_id_before") or "sin_conversacion"
        grouped[str(conversation_id)] += 1
    return [{"conversation_id": cid, "turn_count": count} for cid, count in sorted(grouped.items())]


def duplicate_sandbox_session(
    *,
    source_user_id: str,
    source_session_id: str,
    optimizer_session_id: str,
    source_conversation_id: str | None,
    context_id: str | None = None,
) -> dict[str, Any]:
    source = storage.get_optimizer_state(source_user_id, source_session_id)
    if source is None:
        raise ValueError("sesión optimizer origen no encontrada")

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    sandbox_session_id = f"{source_session_id}__sandbox__{timestamp}"
    sandbox_user_id = source_user_id

    import copy

    cloned = copy.deepcopy(source)
    cloned.session_id = sandbox_session_id
    cloned.user_id = sandbox_user_id
    cloned.world_state = copy.deepcopy(source.world_state)
    context = context_bridge.inherit_or_bind_sandbox_context(
        source_state=source,
        target_state=cloned,
        requested_context_id=context_id,
    )
    cloned.world_state["optimizador_sandbox_meta"] = {
        "optimizer_session_id": optimizer_session_id,
        "source_user_id": source_user_id,
        "source_session_id": source_session_id,
        "source_conversation_id": source_conversation_id,
        "clone_strategy": "full_session_with_preferred_conversation",
        "cloned_at": datetime.now(timezone.utc).isoformat(),
        "preferred_conversation_id": source_conversation_id,
        "base_context": context,
    }

    get_session_store().save(cloned)
    return {
        "session_key": storage.session_key(sandbox_user_id, sandbox_session_id),
        "user_id": sandbox_user_id,
        "session_id": sandbox_session_id,
        "sandbox_meta": cloned.world_state["optimizador_sandbox_meta"],
        "base_context": context,
    }
