from __future__ import annotations

from ..progress_updater import update_progress_state


def progress_updater_node(state: dict) -> dict:
    prev_progress = state.get("progress_state") if isinstance(state.get("progress_state"), dict) else {}
    progress_state, progress_core_debug = update_progress_state(
        prev_progress=prev_progress,
        policy_decision=state.get("policy_decision", {}),
        last_policy_executed=state.get("last_policy_executed"),
        prev_world_state=state.get("prev_world_state", {}),
        world_state=state.get("world_state", {}),
        prev_belief_state=state.get("prev_belief_state", {}),
        belief_state=state.get("belief_state", {}),
        turn_count=state.get("turn_count", 0),
        include_debug=True,
        user_message=str(state.get("user_message", "") or ""),
        semantic_judge=state.get("semantic_judge") if isinstance(state.get("semantic_judge"), dict) else None,
    )
    state["progress_debug"] = progress_core_debug
    state["progress_state"] = progress_state
    return state
