from __future__ import annotations

from typing import Any


_SIGNAL_BUCKETS: tuple[str, ...] = (
    "offers",
    "claims",
    "requests",
    "constraints",
    "interests",
    "concessions",
)


def _bucket_count(world_state: dict[str, Any] | None) -> int:
    buckets = (world_state or {}).get("world_buckets", {}) if isinstance(world_state, dict) else {}
    if not isinstance(buckets, dict):
        return 0
    count = 0
    for key in _SIGNAL_BUCKETS:
        value = buckets.get(key, [])
        if isinstance(value, list):
            count += len(value)
    return count


def compute_clarity_signals(
    world_state: dict[str, Any] | None,
    belief_state: dict[str, Any] | None = None,
    progress_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del belief_state, progress_state
    signal_count = _bucket_count(world_state)
    clarity_vague = signal_count == 0
    return {
        "clarity_vague": clarity_vague,
        "signal_count": signal_count,
        "missing_info": ["world_buckets"] if clarity_vague else [],
    }

