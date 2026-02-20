# backend/negotiation/progress_updater.py
from __future__ import annotations

from .elementos.execution_definitions import OUTCOME_GOOD, OUTCOME_NEUTRAL
from .schemas import (
    BeliefState,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_progress_state,
)
from .world_state_updater import diff_world_state




def _has_info_delta(world_diff: dict) -> bool:
    if not isinstance(world_diff, dict):
        return False
    return any(key != "interaction" for key in world_diff.keys())
def _evaluate_outcome(
    policy_id: str,
    prev_world_state: WorldState,
    world_state: WorldState,
    prev_belief_state: BeliefState | None,
    belief_state: BeliefState,
) -> str:
    del prev_belief_state, belief_state
    if not policy_id:
        return OUTCOME_NEUTRAL
    world_diff = diff_world_state(prev_world_state, world_state)
    return OUTCOME_GOOD if bool(world_diff) else OUTCOME_NEUTRAL


def update_progress_state(
    prev_progress: ProgressState | None,
    policy_decision: PolicyDecision,
    last_policy_executed: PolicyDecision | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    prev_belief_state: BeliefState | None,
    belief_state: BeliefState,
    turn_count: int = 0,
    include_debug: bool = False,
) -> ProgressState | tuple[ProgressState, dict]:
    progress = default_progress_state()
    if prev_progress:
        progress.update(prev_progress)

    previous_policy_id = last_policy_executed.get("policy_id", "") if last_policy_executed else ""
    if previous_policy_id:
        outcome = _evaluate_outcome(
            previous_policy_id,
            prev_world_state,
            world_state,
            prev_belief_state,
            belief_state,
        )
        progress["last_executed_policy_id"] = previous_policy_id
        progress["last_executed_policy_outcome"] = outcome
        last_by_policy = dict(progress.get("policy_last_outcome", {}))
        last_by_policy[previous_policy_id] = outcome
        progress["policy_last_outcome"] = last_by_policy

    policy_id = policy_decision.get("policy_id", "")
    if policy_id:
        attempts = dict(progress.get("policy_attempts", {}))
        attempts[policy_id] = attempts.get(policy_id, 0) + 1
        progress["policy_attempts"] = attempts

        last_chosen_policy_id = progress.get("last_chosen_policy_id", "")
        if last_chosen_policy_id == policy_id:
            progress["turns_in_same_mode"] = int(progress.get("turns_in_same_mode", 0) or 0) + 1
        else:
            progress["turns_in_same_mode"] = 1
        progress["last_chosen_policy_id"] = policy_id

    loop_flags = [str(flag) for flag in progress.get("loop_flags", []) if str(flag).strip()]

    active_plan = progress.get("active_plan") if isinstance(progress.get("active_plan"), dict) else None
    current_plan_id = str((active_plan or {}).get("plan_id", ""))
    prev_plan_id = str(progress.get("last_plan_id", ""))
    if current_plan_id and prev_plan_id and current_plan_id != prev_plan_id:
        plan_changes = int(progress.get("plan_id_changes_window", 0) or 0) + 1
    else:
        plan_changes = max(0, int(progress.get("plan_id_changes_window", 0) or 0) - 1)
    progress["plan_id_changes_window"] = plan_changes
    progress["last_plan_id"] = current_plan_id

    if plan_changes >= 2 and "replan_churn" not in loop_flags:
        loop_flags.append("replan_churn")
    if plan_changes < 2:
        loop_flags = [flag for flag in loop_flags if flag != "replan_churn"]

    judgement = progress.get("last_judgement_status")
    no_progress = int(progress.get("no_progress_same_step_turns", 0) or 0)
    if judgement == "continue_same_step":
        no_progress += 1
    else:
        no_progress = 0
    progress["no_progress_same_step_turns"] = no_progress
    if no_progress >= 3 and "continue_loop" not in loop_flags:
        loop_flags.append("continue_loop")
    if no_progress < 3:
        loop_flags = [flag for flag in loop_flags if flag != "continue_loop"]

    stuck_in_policy_now = int(progress.get("turns_in_same_mode", 0) or 0) >= 2 and progress.get("last_executed_policy_outcome") != OUTCOME_GOOD
    if stuck_in_policy_now and "stuck_in_policy" not in loop_flags:
        loop_flags.append("stuck_in_policy")
    if not stuck_in_policy_now:
        loop_flags = [flag for flag in loop_flags if flag != "stuck_in_policy"]

    progress["loop_flags"] = loop_flags
    progress["last_progress_update_turn"] = turn_count

    if not include_debug:
        return progress

    debug = {
        "anti_loop_signals": {
            "continue_loop_detected": "continue_loop" in loop_flags,
            "continue_loop_counter": int(progress.get("no_progress_same_step_turns", 0) or 0),
            "replan_churn_detected": "replan_churn" in loop_flags,
            "replan_churn_window": int(progress.get("plan_id_changes_window", 0) or 0),
            "plan_id_changes_count": int(progress.get("plan_id_changes_window", 0) or 0),
            "judgement_missing_streak": int(progress.get("judgement_missing_streak", 0) or 0),
        },
    }
    return progress, debug
