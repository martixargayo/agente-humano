from __future__ import annotations

from typing import Any, Dict, Tuple

from .fingerprints import universal_state_fingerprint, world_buckets_fingerprint
from .shared import critical_world_flags, interaction_strong_delta_from_diff, _split_world_diff


def gate_belief(
    world_diff: Dict[str, Any],
    prev_world: Dict[str, Any],
    world: Dict[str, Any],
    turn_count: int,
    last_refresh_turn: int,
    interval: int = 3,
    prev_belief: Dict[str, Any] | None = None,
    prev_universal_fingerprint: str = "",
    prev_world_buckets_fingerprint: str = "",
) -> Tuple[bool, str]:
    if last_refresh_turn == 0:
        return False, "initial_refresh"

    curr_world_buckets_fp = world_buckets_fingerprint(world)
    if prev_world_buckets_fingerprint and curr_world_buckets_fp != prev_world_buckets_fingerprint:
        return False, "world_buckets_changed"

    domain_diff, interaction_diff = _split_world_diff(world_diff)
    world_diff_empty = not bool(domain_diff) and not bool(interaction_diff)
    prev_universal = prev_world.get("universal_domain", {}) if isinstance(prev_world, dict) else {}
    universal = world.get("universal_domain", {}) if isinstance(world, dict) else {}
    prev_open_claims = prev_world.get("open_claims", []) if isinstance(prev_world, dict) else []
    open_claims = world.get("open_claims", []) if isinstance(world, dict) else []

    def _flag_value(state: dict, flag: str) -> object:
        uni = state.get("universal_domain", {}) if isinstance(state, dict) else {}
        neg = state.get("negotiation", {}) if isinstance(state, dict) else {}
        if isinstance(uni, dict) and flag in uni:
            return uni.get(flag)
        if isinstance(neg, dict) and flag in neg:
            return neg.get(flag)
        return None

    critical_change = any(
        _flag_value(prev_world, flag) != _flag_value(world, flag) for flag in critical_world_flags()
    )
    tone_change = prev_universal.get("tone_signal") != universal.get("tone_signal")
    _interaction_strong, interaction_meta = interaction_strong_delta_from_diff(interaction_diff)
    interaction_strong_for_belief = bool(
        interaction_meta.get("escalation_change") or interaction_meta.get("loop_enter")
    )
    prev_health = (
        (prev_belief or {}).get("universal", {}).get("dynamics", {}).get(
            "interaction_health", "stable"
        )
    )
    health_should_refresh = False and bool(prev_health)
    curr_universal_fp = universal_state_fingerprint(world.get("universal_state"))
    fingerprint_changed = bool(
        prev_universal_fingerprint
        and curr_universal_fp
        and prev_universal_fingerprint != curr_universal_fp
    )
    interval_expired = (turn_count - last_refresh_turn) >= interval
    open_claims_changed = bool(prev_open_claims != open_claims)
    if (
        world_diff_empty
        and not critical_change
        and not tone_change
        and not interaction_strong_for_belief
        and not open_claims_changed
        and not fingerprint_changed
        and not health_should_refresh
        and not interval_expired
    ):
        return True, "no_delta_interval_hold"
    reason = "interval_expired" if interval_expired else "delta_or_signal"
    return False, reason
