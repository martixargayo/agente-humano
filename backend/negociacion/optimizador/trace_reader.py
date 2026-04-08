from __future__ import annotations

from typing import Any

from . import storage


def _resolved_optimizer_base_context(turn: dict[str, Any]) -> dict[str, Any]:
    optimizer_meta = turn.get("_optimizador", {}) if isinstance(turn.get("_optimizador"), dict) else {}
    base_context = optimizer_meta.get("base_context", {}) if isinstance(optimizer_meta.get("base_context"), dict) else {}
    context_meta = turn.get("context_meta", {}) if isinstance(turn.get("context_meta"), dict) else {}
    return {
        "flow_id": base_context.get("flow_id") or context_meta.get("flow_id"),
        "context_id": base_context.get("context_id") or context_meta.get("context_id"),
        "context_version": base_context.get("context_version") or context_meta.get("context_version"),
        "context_scope": base_context.get("context_scope") or context_meta.get("context_scope"),
        "official_context_used": base_context.get("official_context_used"),
    }


def list_turns(user_id: str, session_id: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
    turns = [turn for turn in _all_turns_for_session(user_id, session_id) if _match_conversation(turn, conversation_id)]
    out: list[dict[str, Any]] = []
    for idx, turn in enumerate(turns, start=1):
        node_sources = [log.get("source") for log in turn.get("logs", []) if isinstance(log, dict)]
        node_fallbacks = [bool(log.get("fallback_applied", log.get("fallback_used", False))) for log in turn.get("logs", []) if isinstance(log, dict)]
        nodes = turn.get("nodes", {}) if isinstance(turn.get("nodes"), dict) else {}
        single_node_fallback = any(
            isinstance(node, dict) and (node.get("status") in {"clarify", "refuse"} and node.get("model_called") is False)
            for node in nodes.values()
        )
        meta = turn.get("_optimizador", {}) if isinstance(turn.get("_optimizador"), dict) else {}
        versioning = meta.get("versioning", {}) if isinstance(meta.get("versioning"), dict) else {}
        base_context = _resolved_optimizer_base_context(turn)
        out.append(
            {
                "turn_id": turn.get("turn_id"),
                "index": idx,
                "final_status": turn.get("final_status", "unknown"),
                "total_latency_ms": turn.get("total_latency_ms", 0),
                "guardrails_triggered": bool(turn.get("guardrails_triggered", False)),
                "fallback_used": any(node_fallbacks)
                or any(source in {"fallback", "parse_error", "exception", "refusal"} for source in node_sources)
                or single_node_fallback,
                "conversation_id": turn.get("conversation_id_after") or turn.get("conversation_id_before"),
                "has_override": bool(meta.get("applied_overrides")),
                "version": int(versioning.get("version") or 1),
                "base_turn_id": versioning.get("base_turn_id") or turn.get("turn_id"),
                "flow_id": base_context.get("flow_id"),
                "context_id": base_context.get("context_id"),
                "context_version": base_context.get("context_version"),
                "context_scope": base_context.get("context_scope"),
                "official_context_used": base_context.get("official_context_used"),
                "base_context": base_context,
            }
        )
    return out


def get_turn(turn_id: str) -> dict[str, Any] | None:
    for user_id, session_id, _ in storage.iter_optimizer_session_entries():
        turn = _find_turn(user_id, session_id, turn_id)
        if turn:
            return turn
    return None


def get_dialogue(user_id: str, session_id: str) -> list[dict[str, Any]]:
    utterances: list[dict[str, Any]] = []
    for turn in _all_turns_for_session(user_id, session_id):
        user_turn = turn.get("user_turn", {}) if isinstance(turn.get("user_turn"), dict) else {}
        user_text = user_turn.get("raw_text") or user_turn.get("normalized_text") or ""
        utterances.append({"role": "user", "text": user_text, "turn_id": turn.get("turn_id")})
        utterances.append({"role": "assistant", "text": turn.get("final_reply_text", ""), "turn_id": turn.get("turn_id")})
    return utterances


def _all_turns_for_session(user_id: str, session_id: str) -> list[dict[str, Any]]:
    state = storage.get_optimizer_state(user_id, session_id)
    if state is None:
        return []
    turns = storage.resolve_traces(state)
    turns.sort(key=lambda item: item.get("turn_started_at") or item.get("timestamp_utc") or "")
    return turns


def _find_turn(user_id: str, session_id: str, turn_id: str) -> dict[str, Any] | None:
    for turn in _all_turns_for_session(user_id, session_id):
        if turn.get("turn_id") == turn_id:
            return turn
    return None


def _match_conversation(turn: dict[str, Any], conversation_id: str | None) -> bool:
    if not conversation_id:
        return True
    current = turn.get("conversation_id_after") or turn.get("conversation_id_before") or "sin_conversacion"
    return str(current) == conversation_id
