from __future__ import annotations

import hashlib
import json
import warnings
from typing import Any, Dict, Iterable

from ..validation import normalize_universal_state


def stable_allowed_ids_hash(allowed_ids: Iterable[str]) -> str:
    warnings.warn(
        "gating.fingerprints.stable_allowed_ids_hash is deprecated; use legacy.gating_deprecated.",
        DeprecationWarning,
        stacklevel=2,
    )
    from ..legacy.gating_deprecated import stable_allowed_ids_hash as legacy_hash

    return legacy_hash(allowed_ids)


def loop_flags_changed(prev_flags: Iterable[str], current_flags: Iterable[str]) -> bool:
    return sorted(set(prev_flags)) != sorted(set(current_flags))


def interaction_fingerprint(interaction: Dict[str, Any] | None) -> Dict[str, Any]:
    interaction = interaction or {}
    return {
        "implicit_acceptance": bool(interaction.get("implicit_acceptance")),
        "escalation_signal": str(interaction.get("escalation_signal", "none")),
        "loop_hint": bool(interaction.get("loop_hint")),
        "evasion_detected": bool(interaction.get("evasion_detected")),
        "soft_commitment": bool(interaction.get("soft_commitment")),
    }


def universal_state_fingerprint(universal_state: dict) -> str:
    norm = normalize_universal_state(universal_state)
    payload = json.dumps(norm, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()



def world_buckets_fingerprint(world_state: dict | None) -> str:
    world_state = world_state or {}
    buckets = world_state.get("world_buckets") if isinstance(world_state.get("world_buckets"), dict) else {}
    canon = {}
    for bucket in ("offers", "concessions", "constraints", "interests", "claims", "requests", "context"):
        values = buckets.get(bucket, []) if isinstance(buckets.get(bucket), list) else []
        raw_items = []
        for item in values:
            if not isinstance(item, dict):
                continue
            raw = str(item.get("raw_text", "") or item.get("text", "")).strip().lower()
            raw = " ".join(raw.split())
            if raw:
                raw_items.append(raw)
        canon[bucket] = sorted(set(raw_items))
    payload = json.dumps(canon, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
