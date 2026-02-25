from __future__ import annotations

from ..policy_progress import update_policy_state
from .world_node import flush_world_parallel_pending


def policy_progress_node(state: dict) -> dict:
    flush_world_parallel_pending(state)
    progress_state = state.get("progress_state") if isinstance(state.get("progress_state"), dict) else {}
    policy_state, policy_hint, policy_meta = update_policy_state(
        prev_policy_state=progress_state.get("policy_state") if isinstance(progress_state.get("policy_state"), dict) else None,
        world_state=state.get("world_state", {}),
        world_diff=state.get("world_diff", {}),
        belief_state=state.get("belief_state", {}),
        belief_diff=state.get("belief_diff", {}),
        progress_state=progress_state,
        user_message=state.get("user_message", ""),
        turn_count=state.get("turn_count", 0),
    )
    state["progress_state"] = progress_state
    state["policy_hint"] = policy_hint
    state["policy_meta"] = policy_meta
    return state
