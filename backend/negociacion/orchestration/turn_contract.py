from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sessions.state import SessionState

from ..traces.context_meta import build_trace_context_meta
from .flow_config import NegotiationTurnConfig, run_negotiation_cognitive_turn


@dataclass(frozen=True)
class TurnEntryContract:
    entry_surface: str
    entrypoint: str
    overrides_applied: bool
    optimizer_wrapper_used: bool
    new_conversation: bool = False
    clone_used: bool = False


def _resolve_latest_trace(state: SessionState, memory_key: str) -> dict[str, Any] | None:
    traces = state.world_state.get(f"{memory_key}_traces", []) if isinstance(state.world_state, dict) else []
    if not isinstance(traces, list) or not traces:
        return None
    latest = traces[-1]
    return latest if isinstance(latest, dict) else None


def _trace_id(latest: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(latest, dict):
        return None
    value = latest.get(key)
    return value if isinstance(value, str) else None


def execute_turn_with_contract(
    *,
    state: SessionState,
    user_message: str,
    config: NegotiationTurnConfig,
    contract: TurnEntryContract,
) -> tuple[str, SessionState, dict[str, Any]]:
    reply, updated_state = run_negotiation_cognitive_turn(state, user_message, config)

    latest = _resolve_latest_trace(updated_state, config.memory_key)
    context_meta = build_trace_context_meta(state=updated_state, overrides_applied=contract.overrides_applied).model_dump(mode="json")
    if latest is not None:
        latest.setdefault("context_meta", context_meta)
        latest["_entry_contract"] = {
            "entry_surface": contract.entry_surface,
            "entrypoint": contract.entrypoint,
            "overrides_applied": contract.overrides_applied,
            "optimizer_wrapper_used": contract.optimizer_wrapper_used,
            "new_conversation": contract.new_conversation,
            "clone_used": contract.clone_used,
            "context_meta": context_meta,
            "config_snapshot": {
                "memory_key": config.memory_key,
                "thread_mode_default": config.thread_mode_default.value,
                "model_memory": config.model_memory,
                "model_phase_classifier": config.model_phase_classifier,
                "model_planner": config.model_planner,
                "model_executor": config.model_executor,
                "max_recent_messages": config.max_recent_messages,
                "max_executor_recent_turns": config.max_executor_recent_turns,
            },
        }

    canonical = updated_state.world_state.get(config.memory_key, {}) if isinstance(updated_state.world_state, dict) else {}
    thread = canonical.get("openai_thread", {}) if isinstance(canonical, dict) else {}
    meta = {
        "trace_count": len(updated_state.world_state.get(f"{config.memory_key}_traces", []) if isinstance(updated_state.world_state, dict) else []),
        "conversation_id_before": _trace_id(latest, "conversation_id_before"),
        "conversation_id_after": _trace_id(latest, "conversation_id_after") or (thread.get("conversation_id") if isinstance(thread, dict) else None),
        "previous_response_id_before": _trace_id(latest, "previous_response_id_before"),
        "previous_response_id_after": _trace_id(latest, "previous_response_id_after") or (thread.get("previous_response_id") if isinstance(thread, dict) else None),
        "latest_turn_id": latest.get("turn_id") if isinstance(latest, dict) else None,
        "entry_contract": latest.get("_entry_contract") if isinstance(latest, dict) else None,
    }
    return reply, updated_state, meta
