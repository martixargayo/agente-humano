from __future__ import annotations

from ..policy_progress import update_policy_state



def policy_progress_node(state: dict) -> dict:
    progress_state = state.get("progress_state", {})
    policy_plan_judgement = state.get("policy_plan_judgement")
    if not isinstance(policy_plan_judgement, dict):
        policy_plan_judgement = (state.get("world_state") or {}).get("policy_plan_judgement")

    if isinstance(policy_plan_judgement, dict):
        progress_state["judgement_missing_streak"] = 0
    else:
        progress_state["judgement_missing_streak"] = int(progress_state.get("judgement_missing_streak", 0) or 0) + 1
    if isinstance(policy_plan_judgement, dict):
        progress_state["last_judgement_status"] = str(policy_plan_judgement.get("plan_status", ""))
    else:
        progress_state["last_judgement_status"] = "missing"

    policy_state, policy_hint, policy_meta = update_policy_state(
        prev_policy_state=progress_state.get("policy_state"),
        world_state=state["world_state"],
        world_diff=state.get("world_diff", {}),
        belief_state=state["belief_state"],
        belief_diff=state.get("belief_diff", {}),
        progress_state=progress_state,
        user_message=state.get("user_message", ""),
        turn_count=state.get("turn_count", 0),
        last_policy_executed=state.get("last_policy_executed"),
        policy_plan_judgement=policy_plan_judgement,
        active_plan_status=str(progress_state.get("active_plan_status", "none") or "none"),
        judgement_missing_streak=int(progress_state.get("judgement_missing_streak", 0) or 0),
    )
    state["progress_state"] = progress_state
    state["progress_state"]["policy_state"] = policy_state
    state["policy_hint"] = policy_hint
    state["policy_meta"] = policy_meta
    state["policy_plan_judgement"] = policy_plan_judgement
    return state
