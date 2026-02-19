from __future__ import annotations

import os

from ..gate_utils import gate_belief
from ..schemas import default_belief_state, default_progress_state
from ..state.deps import DEFAULT_DEPS


def _should_force_by_stale_urgency(world_state: dict, prev_belief: dict, gate_state: dict, turn_count: int) -> bool:
    stale_turns = int(os.getenv("BELIEF_FORCE_URGENCY_STALE_TURNS", "2"))
    cooldown = int(os.getenv("BELIEF_FORCE_COOLDOWN_TURNS", "2"))
    last_forced = int(gate_state.get("last_belief_forced_turn", 0) or 0)

    wneg = (world_state or {}).get("negotiation", {}) if isinstance(world_state, dict) else {}
    urgency_claimed = bool(wneg.get("urgency_claimed", False))
    if not urgency_claimed:
        return False

    stance = ((prev_belief or {}).get("negotiation", {}) or {}).get("stance", {})
    tp = float(stance.get("time_pressure", 0.5) or 0.5)
    last_tp_turn = int(gate_state.get("last_belief_time_pressure_change_turn", 0) or 0)
    stale = (turn_count - last_tp_turn) >= stale_turns
    not_recently_forced = (turn_count - last_forced) >= cooldown
    return stale and not_recently_forced and tp <= 0.55


def belief_updater_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    prev_belief = state.get("belief_state") or default_belief_state()
    state["prev_belief_state"] = prev_belief
    gate_state = (state.get("progress_state") or {}).get(
        "gate_state", default_progress_state()["gate_state"]
    )
    turn_count = state.get("turn_count", 0) or 0
    conversation_mode = state.get("conversation_mode", "general") or "general"
    extractor_meta = state.get("extractor_meta", {}) or {}
    backstop_reasons = extractor_meta.get("backstop_reasons", []) if isinstance(extractor_meta, dict) else []
    cooldown = int(os.getenv("BELIEF_FORCE_COOLDOWN_TURNS", "2"))
    last_forced = int(gate_state.get("last_belief_forced_turn", 0) or 0)
    force_by_backstop = bool(backstop_reasons) and (turn_count - last_forced >= cooldown)
    force_by_stale_urgency = _should_force_by_stale_urgency(
        state.get("world_state", {}),
        prev_belief,
        gate_state,
        turn_count,
    )

    if force_by_backstop or force_by_stale_urgency:
        belief_skipped = False
        skip_reason = "forced_by_backstop" if force_by_backstop else "forced_by_stale_urgency"
        gate_state["last_belief_forced_turn"] = turn_count
    else:
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
            "forced_by_backstop": False,
            "forced_by_stale_urgency": False,
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
        belief_meta["forced_by_backstop"] = force_by_backstop
        belief_meta["forced_by_stale_urgency"] = force_by_stale_urgency
        stance = ((belief_state or {}).get("negotiation", {}) or {}).get("stance", {})
        prev_stance = ((prev_belief or {}).get("negotiation", {}) or {}).get("stance", {})
        if float(stance.get("time_pressure", 0.5) or 0.5) != float(prev_stance.get("time_pressure", 0.5) or 0.5):
            gate_state["last_belief_time_pressure_change_turn"] = turn_count
    state["belief_state"] = belief_state
    state["belief_update_meta"] = belief_meta
    state["progress_state"]["gate_state"] = gate_state
    return state
