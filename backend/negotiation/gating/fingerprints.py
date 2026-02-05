from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable

from ..validation import normalize_universal_state


def stable_allowed_ids_hash(allowed_ids: Iterable[str]) -> str:
    joined = "|".join(sorted(set(allowed_ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


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
