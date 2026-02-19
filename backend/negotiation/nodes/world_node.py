from __future__ import annotations

import os

from ..gate_utils import (
    gate_world,
    input_shape_features,
    interaction_fingerprint,
    universal_state_fingerprint,
)
from ..mode_inference import update_conversation_mode
from ..schemas import default_progress_state, default_world_state
from ..perception.interaction_signals import _previous_user_message, extract_interaction_signals
from ..world_state_updater import apply_world_skip_fallback, diff_world_state, update_world_state


def world_updater_node(state: dict) -> dict:
    deps = state.get("deps")
    prev_world = state.get("world_state") or default_world_state()
    state["prev_world_state"] = prev_world
    progress_state = state.get("progress_state") or default_progress_state()
    gate_state = progress_state.get("gate_state", default_progress_state()["gate_state"])
    user_message = state.get("user_message", "")
    turn_count = state.get("turn_count", 0) or 0
    modality = state.get("input_modality", "text")
    conversation_mode = progress_state.get("conversation_mode", "general") or "general"
    state["conversation_mode"] = conversation_mode
    prev_text = gate_state.get("prev_user_message", "")
    recent_history = state.get("recent_history")
    if isinstance(recent_history, list):
        prev_text = _previous_user_message(recent_history) or prev_text
    current_features = input_shape_features(
        user_message,
        modality=modality,
        prev_text=prev_text,
        conversation_mode=conversation_mode,
    )
    interaction_current = extract_interaction_signals(
        user_message,
        prev_world,
        recent_history=state.get("recent_history_text", []),
        tone_signal=None,
        prev_interaction=gate_state.get("last_interaction_signals", {}),
    )
    interaction_fingerprint_current = interaction_fingerprint(interaction_current)
    world_skipped, skip_reason, gate_meta = gate_world(
        user_message=user_message,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_world_refresh_turn", 0) or 0),
        prev_features=gate_state.get("input_shape_prev") or {},
        current_features=current_features,
        interaction_fingerprint_prev=gate_state.get("interaction_fingerprint_prev"),
        interaction_fingerprint_current=interaction_fingerprint_current,
        interaction_fingerprint_version=int(
            gate_state.get("interaction_fingerprint_version", 1) or 1
        ),
        interval=int(os.getenv("WORLD_REFRESH_INTERVAL_TURNS", "3")),
        modality=modality,
        conversation_mode=conversation_mode,
    )
    if world_skipped:
        gate_state["world_skip_count"] = int(gate_state.get("world_skip_count", 0) or 0) + 1
        world_state, fallback_meta = apply_world_skip_fallback(prev_world, user_message, turn_count=turn_count)
        state["world_state"] = world_state
        state["world_diff"] = diff_world_state(prev_world, world_state)
        state["extractor_meta"] = {
            "extractor_used": False,
            "extractor_skipped": True,
            "skip_reason": skip_reason,
            "world_gate_features": gate_meta,
            "interaction_updated": True,
            **fallback_meta,
        }
    else:
        world_state, extractor_meta = update_world_state(
            prev_world,
            user_message,
            recent_history=state.get("recent_history_text", ""),
            belief_state=state.get("belief_state") or {},
            turn_count=turn_count,
            conversation_mode=conversation_mode,
            deps=deps,
        )
        gate_state["last_world_refresh_turn"] = turn_count
        state["world_state"] = world_state
        state["world_diff"] = diff_world_state(prev_world, state["world_state"])
        extractor_meta["world_gate_features"] = gate_meta
        extractor_meta["extractor_skipped"] = False
        extractor_meta["interaction_updated"] = True
        state["extractor_meta"] = extractor_meta
    progress_state = update_conversation_mode(progress_state, state.get("world_state", {}), turn_count)
    plan_status = str(progress_state.get("active_plan_status", "none") or "none")
    judgement = (state.get("world_state") or {}).get("policy_plan_judgement")
    judge_no_plan_enabled = os.getenv("WORLD_JUDGE_NO_PLAN_AUTOFILL", "0") == "1"
    if not isinstance(judgement, dict) and plan_status == "none" and judge_no_plan_enabled:
        judgement = {
            "schema_version": "v1",
            "turn_idx": turn_count,
            "plan_presence": "none",
            "plan_status": "interrupted_replan",
            "why": "No hay plan activo; corresponde planificar.",
            "evidence": [],
            "confidence": 0.99,
            "degraded": True,
            "degrade_reason": "no_active_plan",
        }
    state["policy_plan_judgement"] = judgement
    state["progress_state"] = progress_state
    state["conversation_mode"] = progress_state.get("conversation_mode", conversation_mode)
    gate_state["universal_state_fingerprint_prev"] = universal_state_fingerprint(
        state.get("world_state", {}).get("universal_state")
    )
    gate_state["input_shape_prev"] = current_features
    gate_state["last_interaction_signals"] = interaction_current
    gate_state["interaction_fingerprint_prev"] = interaction_fingerprint(interaction_current)
    gate_state["interaction_fingerprint_version"] = int(
        gate_state.get("interaction_fingerprint_version", 1) or 1
    )
    gate_state["prev_user_message"] = user_message
    state["progress_state"]["gate_state"] = gate_state
    return state
