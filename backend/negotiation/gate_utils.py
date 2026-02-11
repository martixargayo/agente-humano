from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, Tuple


_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_PATTERN = re.compile(r"\b\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}\b")
_URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_SYMBOL_PATTERN = re.compile(r"[%€$@#\+\-]")
_ATTACHMENT_HINTS = (
    "foto",
    "fotos",
    "pdf",
    "documento",
    "documentos",
    "adjunto",
    "adjunta",
    "archivo",
    "archivos",
    "imagen",
    "imágenes",
)


def stable_allowed_ids_hash(allowed_ids: Iterable[str]) -> str:
    joined = "|".join(sorted(set(allowed_ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _length_bucket(length: int) -> str:
    if length <= 0:
        return "0"
    if length <= 4:
        return "1_4"
    if length <= 12:
        return "5_12"
    if length <= 40:
        return "13_40"
    return "41_plus"


def _token_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count <= 2:
        return "1_2"
    if count <= 6:
        return "3_6"
    if count <= 14:
        return "7_14"
    return "15_plus"


def input_shape_features(text: str) -> Dict[str, Any]:
    raw = text or ""
    length = len(raw)
    digits_count = sum(1 for ch in raw if ch.isdigit())
    token_count = len(re.findall(r"\w+", raw, flags=re.UNICODE))
    lowered = raw.lower()
    return {
        "len_bucket": _length_bucket(length),
        "token_count_bucket": _token_bucket(token_count),
        "has_digits": digits_count > 0,
        "digits_count_bucket": "0" if digits_count == 0 else ("1_2" if digits_count <= 2 else "3_plus"),
        "has_currency": any(sym in raw for sym in ("€", "$")),
        "has_question": "?" in raw,
        "has_exclamation": "!" in raw,
        "has_url": bool(_URL_PATTERN.search(raw)),
        "has_attachment": any(hint in lowered for hint in _ATTACHMENT_HINTS),
        "has_email": bool(_EMAIL_PATTERN.search(raw)),
        "has_phone": bool(_PHONE_PATTERN.search(raw)),
        "has_symbol": bool(_SYMBOL_PATTERN.search(raw)),
    }


def input_shape_changed_materially(
    prev_features: Dict[str, Any] | None,
    current_features: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    if not prev_features:
        return True, {"reason": "no_prev_features"}
    material_keys = [
        "len_bucket",
        "token_count_bucket",
        "has_digits",
        "digits_count_bucket",
        "has_currency",
        "has_question",
        "has_exclamation",
        "has_url",
        "has_attachment",
    ]
    changed_keys = [
        key for key in material_keys if prev_features.get(key) != current_features.get(key)
    ]
    return bool(changed_keys), {"changed_keys": changed_keys}


def precedence_signature(precedence: Dict[str, Any] | None) -> str:
    prec = precedence or {}
    min_tags = ",".join(sorted(prec.get("min_policy_tags") or []))
    block_tags = ",".join(sorted(prec.get("block_policy_tags") or []))
    return "|".join(
        [
            str(prec.get("mode", "")),
            str(prec.get("phase_floor", "")),
            str(bool(prec.get("allow_closing", True))),
            min_tags,
            block_tags,
        ]
    )


def loop_flags_changed(prev_flags: Iterable[str], current_flags: Iterable[str]) -> bool:
    return sorted(set(prev_flags)) != sorted(set(current_flags))


def critical_world_flags() -> set[str]:
    return {
        "price_mentioned",
        "deadline_claimed",
        "other_buyer_claimed",
        "concession_made",
        "docs_claimed",
        "batna_claimed",
        "urgency_claimed",
        "min_price_claimed",
        "price_firm",
        "evidence_offered",
    }


def _split_world_diff(world_diff: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if "domain" in world_diff or "interaction" in world_diff:
        domain = world_diff.get("domain", {}) or {}
        interaction = world_diff.get("interaction", {}) or {}
        return domain, interaction
    return world_diff, {}


def interaction_strong_delta_from_diff(
    interaction_diff: Dict[str, Any],
) -> Tuple[bool, Dict[str, Any]]:
    if not interaction_diff:
        return False, {}
    meta: Dict[str, Any] = {}
    ia = interaction_diff.get("implicit_acceptance")
    if ia and ia.get("before") is False and ia.get("after") is True:
        meta["implicit_acceptance_rise"] = True
        return True, meta
    esc = interaction_diff.get("escalation_signal")
    if esc and esc.get("before") != esc.get("after") and esc.get("after") in {"up", "down"}:
        meta["escalation_change"] = {"before": esc.get("before"), "after": esc.get("after")}
        return True, meta
    loop = interaction_diff.get("loop_hint")
    if loop and loop.get("before") is False and loop.get("after") is True:
        meta["loop_enter"] = True
        return True, meta
    return False, meta


def interaction_fingerprint(interaction: Dict[str, Any] | None) -> Dict[str, Any]:
    interaction = interaction or {}
    return {
        "implicit_acceptance": bool(interaction.get("implicit_acceptance")),
        "escalation_signal": str(interaction.get("escalation_signal", "none")),
        "loop_hint": bool(interaction.get("loop_hint")),
        "evasion_detected": bool(interaction.get("evasion_detected")),
        "soft_commitment": bool(interaction.get("soft_commitment")),
    }


def gate_world(
    user_message: str,
    turn_count: int,
    last_refresh_turn: int,
    prev_features: Dict[str, Any] | None,
    current_features: Dict[str, Any],
    interaction_fingerprint_prev: Dict[str, Any] | None = None,
    interaction_fingerprint_current: Dict[str, Any] | None = None,
    interaction_fingerprint_version: int = 1,
    interval: int = 3,
) -> Tuple[bool, str, Dict[str, Any]]:
    if not (user_message or "").strip():
        return True, "empty_message", {}
    interval_expired = (turn_count - last_refresh_turn) >= interval
    changed, change_meta = input_shape_changed_materially(prev_features, current_features)
    interaction_changed = False
    if interaction_fingerprint_prev is not None and interaction_fingerprint_current is not None:
        interaction_changed = interaction_fingerprint_prev != interaction_fingerprint_current
    change_meta["interaction_changed"] = interaction_changed
    change_meta["interaction_fingerprint_version"] = interaction_fingerprint_version
    change_meta["interaction_fingerprint_current"] = interaction_fingerprint_current or {}
    if interval_expired or changed:
        reason = "interval_expired" if interval_expired else "input_shape_changed"
        return False, reason, change_meta
    return True, "interval_hold", change_meta


def gate_belief(
    world_diff: Dict[str, Any],
    prev_world: Dict[str, Any],
    world: Dict[str, Any],
    turn_count: int,
    last_refresh_turn: int,
    interval: int = 3,
    prev_belief: Dict[str, Any] | None = None,
) -> Tuple[bool, str]:
    if last_refresh_turn == 0:
        return False, "initial_refresh"
    domain_diff, interaction_diff = _split_world_diff(world_diff)
    world_diff_empty = not bool(domain_diff) and not bool(interaction_diff)
    critical_change = any(
        prev_world.get(flag) != world.get(flag) for flag in critical_world_flags()
    )
    tone_change = prev_world.get("tone_signal") != world.get("tone_signal")
    interaction_strong, interaction_meta = interaction_strong_delta_from_diff(interaction_diff)
    interaction_strong_for_belief = bool(
        interaction_meta.get("escalation_change") or interaction_meta.get("loop_enter")
    )
    prev_health = (prev_belief or {}).get("dynamics", {}).get("interaction_health", "stable")
    health_should_refresh = (
        prev_health in {"tense", "stalled"}
        and (world.get("interaction") or {}).get("escalation_signal") == "down"
    )
    interval_expired = (turn_count - last_refresh_turn) >= interval
    if (
        world_diff_empty
        and not critical_change
        and not tone_change
        and not interaction_strong_for_belief
        and not health_should_refresh
        and not interval_expired
    ):
        return True, "no_delta_interval_hold"
    reason = "interval_expired" if interval_expired else "delta_or_signal"
    return False, reason


def gate_phase_policy(
    world_diff: Dict[str, Any],
    precedence_changed: bool,
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
        or precedence_changed
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
