# backend/negotiation/progress_updater.py
from __future__ import annotations

from .schemas import PolicyDecision, ProgressState, default_progress_state


def update_progress_state(
    prev_progress: ProgressState | None,
    policy_decision: PolicyDecision,
) -> ProgressState:
    progress = default_progress_state()
    if prev_progress:
        progress.update(prev_progress)

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

    return progress
