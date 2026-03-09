from __future__ import annotations

from typing import Any
from datetime import datetime, timezone

from sessions.state import get_session_state, SessionState

from ..orchestration.flow_config import build_negotiation_pipeline_config, run_negotiation_cognitive_turn
from ..state.canonical_state import build_default_canonical_state
from ..state.shared_types import ThreadMode
from . import datasets_bridge, evals_bridge, experiments_bridge, guardrails_bridge, session_bridge, storage, trace_reader
from .prompts_bridge import list_prompts as _list_prompts

def _apply_contextual_state_overrides(state: Any, config: Any, entries: list[dict[str, Any]]) -> None:
    persona_entry = next((entry for entry in entries if entry.get("category") == "contextual" and entry.get("key") == "persona"), None)
    if not persona_entry:
        return
    memory_key = config.memory_key
    raw = state.world_state.get(memory_key)
    if not isinstance(raw, dict):
        raw = build_default_canonical_state(session_id=state.session_id, user_id=state.user_id, thread_mode=ThreadMode.conversation).model_dump(mode="json")
    persona_value = persona_entry.get("value")
    if not isinstance(persona_value, dict):
        return
    policy = persona_value.get("policy")
    expressive = persona_value.get("expressive")
    if not isinstance(policy, dict) or not isinstance(expressive, dict):
        return
    import copy

    updated = copy.deepcopy(raw)
    updated["persona"] = {"policy": policy, "expressive": expressive}
    state.world_state[memory_key] = updated


def list_sessions() -> list[dict[str, Any]]:
    return session_bridge.list_sessions()


def list_conversations(user_id: str, session_id: str) -> list[dict[str, Any]]:
    return session_bridge.list_conversations(user_id, session_id)


def list_turns(user_id: str, session_id: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
    return trace_reader.list_turns(user_id=user_id, session_id=session_id, conversation_id=conversation_id)


def get_turn(turn_id: str) -> dict[str, Any] | None:
    return trace_reader.get_turn(turn_id)


def get_dialogue(user_id: str, session_id: str) -> list[dict[str, Any]]:
    return trace_reader.get_dialogue(user_id=user_id, session_id=session_id)


def get_guardrails(turn_id: str) -> dict[str, Any] | None:
    turn = get_turn(turn_id)
    return guardrails_bridge.summarize_guardrails(turn) if turn else None


def duplicate_sandbox_session(
    *,
    optimizer_session_id: str,
    source_user_id: str,
    source_session_id: str,
    source_conversation_id: str | None,
) -> dict[str, Any]:
    return session_bridge.duplicate_sandbox_session(
        source_user_id=source_user_id,
        source_session_id=source_session_id,
        source_conversation_id=source_conversation_id,
        optimizer_session_id=optimizer_session_id,
    )


def new_conversation_session(*, optimizer_session_id: str, user_id: str, session_id: str) -> dict[str, Any]:
    state = get_session_state(user_id=user_id, session_id=session_id)
    new_session_id = f"{session_id}__newconv__{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    new_state = SessionState(user_id=user_id, session_id=new_session_id)
    new_state.world_state["optimizador_sandbox_meta"] = {
        "optimizer_session_id": optimizer_session_id,
        "source_user_id": user_id,
        "source_session_id": session_id,
        "source_conversation_id": None,
        "clone_strategy": "new_conversation_clean_start",
        "cloned_at": datetime.now(timezone.utc).isoformat(),
        "preferred_conversation_id": None,
    }
    from sessions.state import SESSIONS
    SESSIONS[(user_id, new_session_id)] = new_state
    _ = state
    return {
        "session_key": storage.session_key(user_id, new_session_id),
        "user_id": user_id,
        "session_id": new_session_id,
        "sandbox_meta": new_state.world_state["optimizador_sandbox_meta"],
    }


def run_sandbox_turn(
    *,
    optimizer_session_id: str,
    user_id: str,
    session_id: str,
    message: str,
    conversation_id: str | None,
    scope_turn_id: str | None,
    repeat_from_turn_id: str | None,
) -> dict[str, Any]:
    state = get_session_state(user_id=user_id, session_id=session_id)
    base_config = build_negotiation_pipeline_config()
    resolved_entries = experiments_bridge.resolve_entries(
        optimizer_session_id=optimizer_session_id,
        conversation_id=conversation_id,
        turn_id=scope_turn_id,
    )
    config, tempdir = experiments_bridge.apply_overrides(base_config, resolved_entries)
    _apply_contextual_state_overrides(state, config, resolved_entries)
    try:
        reply, _ = run_negotiation_cognitive_turn(state, message, config)
    finally:
        if tempdir is not None:
            tempdir.cleanup()

    traces = storage.resolve_traces(state)
    latest = traces[-1] if traces else None
    versioning = _resolve_versioning(state, latest, repeat_from_turn_id)
    if latest is not None:
        latest["_optimizador"] = {
            "optimizer_session_id": optimizer_session_id,
            "used_overrides": bool(resolved_entries),
            "applied_overrides": experiments_bridge.describe_effective_overrides(resolved_entries),
            "mode": experiments_bridge.get_state(optimizer_session_id).get("mode", "mirror"),
            "session_key": storage.session_key(user_id, session_id),
            "conversation_id": conversation_id,
            "versioning": versioning,
        }

    turns = list_turns(user_id, session_id, conversation_id=conversation_id)
    selected_turn = turns[-1] if turns else None
    return {
        "reply": reply,
        "turn": selected_turn,
        "turn_title": derive_turn_title(latest, turns) if latest else None,
        "effective_overrides": experiments_bridge.describe_effective_overrides(resolved_entries),
    }


def _resolve_versioning(state: Any, latest_turn: dict[str, Any] | None, repeat_from_turn_id: str | None) -> dict[str, Any]:
    if latest_turn is None:
        return {"base_turn_id": None, "version": 1}

    traces = storage.resolve_traces(state)
    if not repeat_from_turn_id:
        return {"base_turn_id": latest_turn.get("turn_id"), "version": 1}

    source_turn = next((t for t in traces if t.get("turn_id") == repeat_from_turn_id), None)
    base_turn_id = repeat_from_turn_id
    if isinstance(source_turn, dict):
        meta = source_turn.get("_optimizador", {}) if isinstance(source_turn.get("_optimizador"), dict) else {}
        versioning = meta.get("versioning", {}) if isinstance(meta.get("versioning"), dict) else {}
        base_turn_id = versioning.get("base_turn_id") or repeat_from_turn_id

    max_version = 1
    for t in traces:
        meta = t.get("_optimizador", {}) if isinstance(t.get("_optimizador"), dict) else {}
        versioning = meta.get("versioning", {}) if isinstance(meta.get("versioning"), dict) else {}
        if versioning.get("base_turn_id") == base_turn_id:
            max_version = max(max_version, int(versioning.get("version") or 1))

    return {"base_turn_id": base_turn_id, "version": max_version + 1}


def derive_turn_title(turn: dict[str, Any], turns: list[dict[str, Any]]) -> str:
    turn_id = turn.get("turn_id")
    index = next((item.get("index") for item in turns if item.get("turn_id") == turn_id), None)
    meta = turn.get("_optimizador", {}) if isinstance(turn.get("_optimizador"), dict) else {}
    versioning = meta.get("versioning", {}) if isinstance(meta.get("versioning"), dict) else {}
    version = versioning.get("version") or 1
    return f"Turno {index or '?'} · v{version}"


def list_prompts() -> list[dict[str, str]]:
    return _list_prompts()


def run_eval(action: str) -> dict[str, Any]:
    return evals_bridge.run_eval(action)


def save_case(turn_id: str, family: str, tags: list[str], notes: str) -> dict[str, Any]:
    turn = get_turn(turn_id)
    if not turn:
        raise ValueError("turn_id no encontrado")
    return datasets_bridge.save_case(turn, family=family, tags=tags, notes=notes)


def list_cases() -> list[dict[str, Any]]:
    return datasets_bridge.list_cases()


def compare_turns(turn_a: str, turn_b: str) -> dict[str, Any]:
    a = get_turn(turn_a)
    b = get_turn(turn_b)
    if not a or not b:
        raise ValueError("Turnos no encontrados")

    a_meta = a.get("_optimizador", {}) if isinstance(a.get("_optimizador"), dict) else {}
    b_meta = b.get("_optimizador", {}) if isinstance(b.get("_optimizador"), dict) else {}

    a_overrides = a_meta.get("applied_overrides") if isinstance(a_meta.get("applied_overrides"), dict) else {"prompt": {}, "config": {}, "contextual": {}}
    b_overrides = b_meta.get("applied_overrides") if isinstance(b_meta.get("applied_overrides"), dict) else {"prompt": {}, "config": {}, "contextual": {}}

    return {
        "a": _comparison_block(a),
        "b": _comparison_block(b),
        "relationship": {
            "a_is_experiment": bool(a_meta.get("used_overrides")),
            "b_is_experiment": bool(b_meta.get("used_overrides")),
            "experiment_kind": _experiment_kind(a_meta, b_meta),
            "same_optimizer_session": a_meta.get("optimizer_session_id") == b_meta.get("optimizer_session_id"),
            "a_optimizer_session": a_meta.get("optimizer_session_id"),
            "b_optimizer_session": b_meta.get("optimizer_session_id"),
        },
        "effective_overrides": {
            "a": a_overrides,
            "b": b_overrides,
            "category_differences": {
                "prompt": sorted(set(a_overrides.get("prompt", {}).keys()) ^ set(b_overrides.get("prompt", {}).keys())),
                "config": sorted(set(a_overrides.get("config", {}).keys()) ^ set(b_overrides.get("config", {}).keys())),
                "contextual": sorted(set(a_overrides.get("contextual", {}).keys()) ^ set(b_overrides.get("contextual", {}).keys())),
            },
        },
        "diff": {
            "final_status_changed": a.get("final_status") != b.get("final_status"),
            "latency_delta_ms": (b.get("total_latency_ms") or 0) - (a.get("total_latency_ms") or 0),
            "reply_changed": a.get("final_reply_text") != b.get("final_reply_text"),
            "guardrails": {
                "input_decision_changed": a.get("input_guardrail_decision") != b.get("input_guardrail_decision"),
                "output_decision_changed": a.get("output_guardrail_decision") != b.get("output_guardrail_decision"),
                "input_trigger_changed": a.get("input_guardrail_triggered") != b.get("input_guardrail_triggered"),
                "output_trigger_changed": a.get("output_guardrail_triggered") != b.get("output_guardrail_triggered"),
                "output_rewrite_changed": a.get("output_guardrail_rewrite_applied") != b.get("output_guardrail_rewrite_applied"),
                "input_moderation_changed": a.get("input_moderation_used") != b.get("input_moderation_used"),
                "output_moderation_changed": a.get("output_moderation_used") != b.get("output_moderation_used"),
            },
            "node_changes": _node_diff(a, b),
        },
    }


def _comparison_block(turn: dict[str, Any]) -> dict[str, Any]:
    nodes = turn.get("nodes", {}) if isinstance(turn.get("nodes"), dict) else {}
    return {
        "turn_id": turn.get("turn_id"),
        "conversation_id": turn.get("conversation_id_after") or turn.get("conversation_id_before"),
        "final_reply": turn.get("final_reply_text"),
        "final_status": turn.get("final_status"),
        "latency_ms": turn.get("total_latency_ms"),
        "guardrails": {
            "input": turn.get("input_guardrail_decision"),
            "output": turn.get("output_guardrail_decision"),
            "input_triggered": turn.get("input_guardrail_triggered"),
            "output_triggered": turn.get("output_guardrail_triggered"),
            "output_rewrite": turn.get("output_guardrail_rewrite_applied"),
            "input_moderation_used": turn.get("input_moderation_used"),
            "output_moderation_used": turn.get("output_moderation_used"),
        },
        "fallback_or_error": [
            node_name
            for node_name, node in nodes.items()
            if isinstance(node, dict) and node.get("source") in {"fallback", "parse_error", "exception", "refusal"}
        ],
        "nodes": {
            node_name: {
                "status": node.get("status"),
                "source": node.get("source"),
                "latency_ms": node.get("latency_ms"),
            }
            for node_name, node in nodes.items()
            if isinstance(node, dict)
        },
        "optimizer": turn.get("_optimizador", {}),
    }


def _experiment_kind(a_meta: dict[str, Any], b_meta: dict[str, Any]) -> str:
    a_exp = bool(a_meta.get("used_overrides"))
    b_exp = bool(b_meta.get("used_overrides"))
    if not a_exp and b_exp:
        return "baseline_vs_experiment"
    if a_exp and not b_exp:
        return "experiment_vs_baseline"
    if a_exp and b_exp:
        return "experiment_vs_experiment"
    return "baseline_vs_baseline"


def _node_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    a_nodes = a.get("nodes", {}) if isinstance(a.get("nodes"), dict) else {}
    b_nodes = b.get("nodes", {}) if isinstance(b.get("nodes"), dict) else {}
    names = sorted(set(a_nodes.keys()) | set(b_nodes.keys()))
    diff: dict[str, dict[str, Any]] = {}
    for name in names:
        a_node = a_nodes.get(name, {}) if isinstance(a_nodes.get(name), dict) else {}
        b_node = b_nodes.get(name, {}) if isinstance(b_nodes.get(name), dict) else {}
        item = {
            "a_status": a_node.get("status"),
            "b_status": b_node.get("status"),
            "a_source": a_node.get("source"),
            "b_source": b_node.get("source"),
            "a_latency_ms": a_node.get("latency_ms"),
            "b_latency_ms": b_node.get("latency_ms"),
            "a_prompt_version": a_node.get("prompt_version"),
            "b_prompt_version": b_node.get("prompt_version"),
            "a_output_summary": a_node.get("output_summary"),
            "b_output_summary": b_node.get("output_summary"),
        }
        if any(item[k] != item[k.replace("a_", "b_")] for k in ["a_status", "a_source", "a_latency_ms", "a_prompt_version", "a_output_summary"]):
            diff[name] = item
    return diff
