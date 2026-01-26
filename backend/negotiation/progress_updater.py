# backend/negotiation/progress_updater.py
from __future__ import annotations

from .schemas import BeliefState, PolicyDecision, ProgressState, WorldState, default_progress_state


def _evaluate_outcome(
    policy_id: str,
    world_state: WorldState,
    belief_state: BeliefState,
) -> str:
    if not policy_id:
        return "neutral"

    health = belief_state.get("dynamics", {}).get("interaction_health", "stable")

    if policy_id == "info_extract_critical":
        if world_state.get("docs_claimed") or world_state.get("deadline_claimed"):
            return "good"
        if world_state.get("price_mentioned"):
            return "neutral"
        return "neutral"

    if policy_id == "delay_price_discussion":
        if world_state.get("price_mentioned"):
            return "bad"
        return "good"

    if policy_id == "deescalate_tension":
        if health == "stable":
            return "good"
        if health == "tense":
            return "bad"
        return "neutral"

    if policy_id == "rapport_build":
        if health == "stable":
            return "good"
        return "neutral"

    if policy_id == "test_credibility":
        if world_state.get("other_buyer_claimed") or world_state.get("deadline_claimed"):
            return "good"
        return "neutral"

    if policy_id in {"tradeoff_offer", "hold_position"}:
        if world_state.get("concession_made"):
            return "good"
        return "neutral"

    if policy_id == "challenge_anchor_indirect":
        if belief_state.get("stance", {}).get("seller_flexibility", 0.0) > 0.6:
            return "good"
        return "neutral"

    if policy_id == "close_with_conditions":
        if world_state.get("concession_made"):
            return "good"
        return "neutral"

    return "neutral"


def update_progress_state(
    prev_progress: ProgressState | None,
    policy_decision: PolicyDecision,
    world_state: WorldState,
    belief_state: BeliefState,
) -> ProgressState:
    progress = default_progress_state()
    if prev_progress:
        progress.update(prev_progress)

    previous_policy_id = prev_progress.get("last_policy_id", "") if prev_progress else ""
    if previous_policy_id:
        progress["last_policy_outcome"] = _evaluate_outcome(
            previous_policy_id, world_state, belief_state
        )

    policy_id = policy_decision.get("policy_id", "")
    if policy_id:
        progress["last_policy_id"] = policy_id
        attempts = dict(progress.get("policy_attempts", {}))
        attempts[policy_id] = attempts.get(policy_id, 0) + 1
        progress["policy_attempts"] = attempts

        if prev_progress and prev_progress.get("last_policy_id") == policy_id:
            progress["turns_in_same_mode"] = prev_progress.get("turns_in_same_mode", 0) + 1
        else:
            progress["turns_in_same_mode"] = 1

    loop_flags = list(progress.get("loop_flags", []))
    if progress.get("turns_in_same_mode", 0) >= 2 and progress.get("last_policy_outcome") != "good":
        if "stuck_in_policy" not in loop_flags:
            loop_flags.append("stuck_in_policy")
    progress["loop_flags"] = loop_flags

    return progress
