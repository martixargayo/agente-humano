from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, Tuple

from ..gating.shared import (
    _split_world_diff,
    critical_world_flags,
    interaction_strong_delta_from_diff,
)

__all__ = ["gate_phase_policy", "select_policy_id_on_skip", "stable_allowed_ids_hash"]


def stable_allowed_ids_hash(allowed_ids: Iterable[str]) -> str:
    joined = "|".join(sorted(set(allowed_ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def gate_phase_policy(
    world_diff: Dict[str, Any],
    intent_transition_present: bool,
    loop_flags_changed_flag: bool,
    allowed_ids_hash_changed: bool,
    turn_count: int,
    last_refresh_turn: int,
    interval: int = 2,
) -> Tuple[bool, str, Dict[str, Any]]:
    domain_diff, interaction_diff = _split_world_diff(world_diff)
    critical_diff = any(key in domain_diff for key in critical_world_flags())
    interaction_strong, interaction_meta = interaction_strong_delta_from_diff(interaction_diff)
    strong_signals = (
        critical_diff
        or intent_transition_present
        or loop_flags_changed_flag
        or allowed_ids_hash_changed
        or interaction_strong
    )
    interval_expired = (turn_count - last_refresh_turn) >= interval
    if interval_expired or strong_signals:
        reason = "interval_expired" if interval_expired else "strong_signals"
        return False, reason, {"interaction_meta": interaction_meta}
    return True, "interval_hold", {"interaction_meta": interaction_meta}


def select_policy_id_on_skip(
    last_policy_chosen: str,
    allowed_policy_ids: list[str],
    policy_attempts: Dict[str, int] | None,
    loop_flags: Iterable[str],
    safe_neutral_policy_id: str,
    max_attempts: int = 3,
) -> Tuple[str, str]:
    attempts = policy_attempts or {}
    loop_flags_clean = not list(loop_flags)
    if (
        last_policy_chosen
        and last_policy_chosen in allowed_policy_ids
        and loop_flags_clean
        and attempts.get(last_policy_chosen, 0) < max_attempts
    ):
        return last_policy_chosen, "reuse_last_policy"
    if safe_neutral_policy_id in allowed_policy_ids:
        return safe_neutral_policy_id, "safe_neutral_fallback"
    fallback = allowed_policy_ids[0] if allowed_policy_ids else safe_neutral_policy_id
    return fallback, "safe_neutral_missing"
