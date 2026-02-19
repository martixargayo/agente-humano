from __future__ import annotations

import hashlib
import json
import os

from ..gate_utils import gate_belief, world_buckets_fingerprint
from ..schemas import default_belief_state, default_progress_state
from ..state.deps import DEFAULT_DEPS


def _state_fingerprint(value: dict) -> str:
    payload = json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def belief_updater_node(state: dict) -> dict:
    deps = state.get("deps", DEFAULT_DEPS)
    prev_belief = state.get("belief_state") or default_belief_state()
    state["prev_belief_state"] = prev_belief
    gate_state = (state.get("progress_state") or {}).get(
        "gate_state", default_progress_state()["gate_state"]
    )
    turn_count = state.get("turn_count", 0) or 0
    conversation_mode = state.get("conversation_mode", "general") or "general"
    prev_world_buckets_fp = str(gate_state.get("world_buckets_fingerprint_prev", ""))
    curr_world_buckets_fp = world_buckets_fingerprint(state.get("world_state", {}))
    prev_belief_fp = _state_fingerprint(prev_belief)

    belief_skipped, skip_reason = gate_belief(
        world_diff=state.get("world_diff", {}),
        prev_world=state.get("prev_world_state", {}),
        world=state.get("world_state", {}),
        prev_belief=prev_belief,
        turn_count=turn_count,
        last_refresh_turn=int(gate_state.get("last_belief_refresh_turn", 0) or 0),
        interval=int(os.getenv("BELIEF_REFRESH_INTERVAL_TURNS", "3")),
        prev_universal_fingerprint=str(gate_state.get("universal_state_fingerprint_prev", "")),
        prev_world_buckets_fingerprint=str(gate_state.get("world_buckets_fingerprint_prev", "")),
    )
    if belief_skipped:
        gate_state["belief_skip_count"] = int(gate_state.get("belief_skip_count", 0) or 0) + 1
        belief_state = prev_belief
        belief_meta = {
            "belief_update_failed": False,
            "belief_update_error": "",
            "belief_update_skipped": True,
            "skip_reason": skip_reason,
            "belief_node_entered": True,
            "belief_updater_invoked": False,
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
        belief_meta["belief_node_entered"] = True
        belief_meta["belief_updater_invoked"] = True
        belief_meta["belief_gate_skip_reason"] = skip_reason

    curr_belief_fp = _state_fingerprint(belief_state)
    belief_meta["belief_gate_decision"] = {
        "skipped": bool(belief_skipped),
        "reason": str(skip_reason),
        "prev_world_buckets_fp": prev_world_buckets_fp or None,
        "curr_world_buckets_fp": curr_world_buckets_fp or None,
        "prev_belief_fp": prev_belief_fp or None,
        "curr_belief_fp": curr_belief_fp or None,
    }
    if belief_skipped:
        belief_meta["belief_gate_skip_reason"] = str(skip_reason)

    gate_state["world_buckets_fingerprint_prev"] = curr_world_buckets_fp
    state["belief_state"] = belief_state
    state["belief_update_meta"] = belief_meta
    state["progress_state"]["gate_state"] = gate_state
    return state
