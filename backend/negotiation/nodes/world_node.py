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
from ..world_state_updater import (
    _previous_user_message,
    diff_world_state,
    extract_interaction_signals,
    update_world_state,
)


def world_updater_node(state: dict) -> dict:
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
        world_state = dict(prev_world)
        world_state["interaction"] = interaction_current
        state["world_state"] = world_state
        state["world_diff"] = diff_world_state(prev_world, world_state)
        state["extractor_meta"] = {
            "extractor_used": False,
            "extractor_skipped": True,
            "skip_reason": skip_reason,
            "world_gate_features": gate_meta,
            "interaction_updated": True,
        }
    else:
        force_llm = skip_reason == "interval_expired"
        extractor_mode = gate_meta.get("extractor_mode", "regex")
        world_state, extractor_meta = update_world_state(
            prev_world,
            user_message,
            recent_history=state.get("recent_history_text", ""),
            belief_state=state.get("belief_state") or {},
            turn_count=turn_count,
            force_llm=force_llm,
            extractor_mode=extractor_mode,
            conversation_mode=conversation_mode,
        )
        gate_state["last_world_refresh_turn"] = turn_count
        state["world_state"] = world_state
        state["world_diff"] = diff_world_state(prev_world, state["world_state"])
        extractor_meta["world_gate_features"] = gate_meta
        extractor_meta["extractor_skipped"] = False
        extractor_meta["interaction_updated"] = True
        state["extractor_meta"] = extractor_meta
    progress_state = update_conversation_mode(progress_state, state.get("world_state", {}), turn_count)
    state["progress_state"] = progress_state
    state["conversation_mode"] = progress_state.get("conversation_mode", conversation_mode)
    gate_state["universal_state_fingerprint_prev"] = universal_state_fingerprint(
        state.get("world_state", {}).get("universal_state")
    )
    gate_state["input_shape_prev"] = current_features
    gate_state["interaction_fingerprint_prev"] = interaction_fingerprint(
        state.get("world_state", {}).get("interaction", {})
    )
    gate_state["interaction_fingerprint_version"] = int(
        gate_state.get("interaction_fingerprint_version", 1) or 1
    )
    gate_state["prev_user_message"] = user_message
    state["progress_state"]["gate_state"] = gate_state
    return state
