from __future__ import annotations

from ..policy_progress import update_policy_state


def policy_progress_node(state: dict) -> dict:
    policy_state, policy_hint, policy_meta = update_policy_state(
        prev_policy_state=state.get("progress_state", {}).get("policy_state"),
        world_state=state["world_state"],
        world_diff=state.get("world_diff", {}),
        belief_state=state["belief_state"],
        belief_diff=state.get("belief_diff", {}),
        progress_state=state.get("progress_state", {}),
        user_message=state.get("user_message", ""),
        turn_count=state.get("turn_count", 0),
        last_policy_executed=state.get("last_policy_executed"),
    )
    state["progress_state"]["policy_state"] = policy_state
    state["policy_hint"] = policy_hint
    state["policy_meta"] = policy_meta
    return state
