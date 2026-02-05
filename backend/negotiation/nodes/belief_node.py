from __future__ import annotations

import os

from ..gate_utils import gate_belief
from ..schemas import default_belief_state, default_progress_state
from ..state.deps import DEFAULT_DEPS


def belief_updater_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    prev_belief = state.get("belief_state") or default_belief_state()
    state["prev_belief_state"] = prev_belief
    gate_state = (state.get("progress_state") or {}).get(
        "gate_state", default_progress_state()["gate_state"]
    )
    turn_count = state.get("turn_count", 0) or 0
    conversation_mode = state.get("conversation_mode", "general") or "general"
    belief_skipped, skip_reason = gate_belief(
        world_diff=state.get("world_diff", {}),
        prev_world=state.get("prev_world_state", {}),
        world=state.get("world_state", {}),
        prev_belief=prev_belief,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_belief_refresh_turn", 0) or 0),
        interval=int(os.getenv("BELIEF_REFRESH_INTERVAL_TURNS", "3")),
        prev_universal_fingerprint=str(gate_state.get("universal_state_fingerprint_prev", "")),
    )
    if belief_skipped:
        gate_state["belief_skip_count"] = int(gate_state.get("belief_skip_count", 0) or 0) + 1
        belief_state = prev_belief
        belief_meta = {
            "belief_update_failed": False,
            "belief_update_error": "",
            "belief_update_skipped": True,
            "skip_reason": skip_reason,
        }
    else:
        belief_state, belief_meta = deps.update_belief_state(
            prev_belief_state=prev_belief,
            prev_world_state=state["prev_world_state"],
            world_state=state["world_state"],
            world_diff=state.get("world_diff", {}),
            last_policy_executed=state.get("last_policy_executed"),
            last_assistant_message=state.get("last_assistant_message", ""),
            user_message=state.get("user_message", ""),
            context_snippet=state.get("recent_history_text", ""),
            extractor_meta=state.get("extractor_meta", {}),
            force_update=True,
            conversation_mode=conversation_mode,
        )
        gate_state["last_belief_refresh_turn"] = turn_count
    state["belief_state"] = belief_state
    state["belief_update_meta"] = belief_meta
    state["progress_state"]["gate_state"] = gate_state
    return state
