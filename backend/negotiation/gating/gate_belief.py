from __future__ import annotations

from typing import Any, Dict, Tuple

from .fingerprints import universal_state_fingerprint
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
) -> Tuple[bool, str]:
    if last_refresh_turn == 0:
        return False, "initial_refresh"
    domain_diff, interaction_diff = _split_world_diff(world_diff)
    world_diff_empty = not bool(domain_diff) and not bool(interaction_diff)
    prev_universal = prev_world.get("universal_domain", {}) if isinstance(prev_world, dict) else {}
    prev_negotiation = prev_world.get("negotiation", {}) if isinstance(prev_world, dict) else {}
    universal = world.get("universal_domain", {}) if isinstance(world, dict) else {}
    negotiation = world.get("negotiation", {}) if isinstance(world, dict) else {}

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
    interaction_strong, interaction_meta = interaction_strong_delta_from_diff(interaction_diff)
    interaction_strong_for_belief = bool(
        interaction_meta.get("escalation_change") or interaction_meta.get("loop_enter")
    )
    interaction_universal_signal = False
    prev_health = (
        (prev_belief or {}).get("universal", {}).get("dynamics", {}).get(
            "interaction_health", "stable"
        )
    )
    health_should_refresh = False
    curr_universal_fp = universal_state_fingerprint(world.get("universal_state"))
    fingerprint_changed = bool(
        prev_universal_fingerprint
        and curr_universal_fp
        and prev_universal_fingerprint != curr_universal_fp
    )
    interval_expired = (turn_count - last_refresh_turn) >= interval
    if (
        world_diff_empty
        and not critical_change
        and not tone_change
        and not interaction_strong_for_belief
        and not interaction_universal_signal
        and not fingerprint_changed
        and not health_should_refresh
        and not interval_expired
    ):
        return True, "no_delta_interval_hold"
    reason = "interval_expired" if interval_expired else "delta_or_signal"
    return False, reason
