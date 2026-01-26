# backend/negotiation/validation.py
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from .schemas import (
    BeliefState,
    InteractionHealth,
    PolicyDecision,
    ProgressState,
    RiskPosture,
    ToneSignal,
    WorldState,
    default_belief_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)


_ALLOWED_HEALTH: set[InteractionHealth] = {"stable", "tense", "stalled"}
_ALLOWED_RISK: set[RiskPosture] = {"low", "mid", "high"}
_ALLOWED_TONE: set[ToneSignal] = {"neutral", "friendly", "tense"}


def _clamp(value: float, min_value: float = 0.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_str_list(values: object, max_items: int | None = None) -> List[str]:
    if not isinstance(values, list):
        return []
    cleaned = [str(item).strip() for item in values if str(item).strip()]
    if max_items is not None:
        return cleaned[:max_items]
    return cleaned


def _unique_list(values: Iterable[str], max_items: int | None = None) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if max_items is not None and len(result) >= max_items:
            break
    return result


def normalize_world_state(raw: object) -> Tuple[WorldState, List[str]]:
    base = default_world_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("world_state_no_dict")
        return base, issues
    if "tone_signal" not in raw:
        issues.append("tone_signal_missing")
        return base, issues

    base["price_mentioned"] = bool(raw.get("price_mentioned", base["price_mentioned"]))
    price_value = raw.get("price_value", base["price_value"])
    if price_value is None:
        base["price_value"] = None
    else:
        base["price_value"] = _coerce_float(price_value, 0.0)

    base["deadline_claimed"] = bool(raw.get("deadline_claimed", base["deadline_claimed"]))
    base["deadline_text"] = str(raw.get("deadline_text", base["deadline_text"])).strip()
    base["other_buyer_claimed"] = bool(raw.get("other_buyer_claimed", base["other_buyer_claimed"]))
    base["concession_made"] = bool(raw.get("concession_made", base["concession_made"]))
    base["concession_text"] = str(raw.get("concession_text", base["concession_text"])).strip()
    base["docs_claimed"] = bool(raw.get("docs_claimed", base["docs_claimed"]))
    base["docs_types"] = _unique_list(_coerce_str_list(raw.get("docs_types", [])))

    tone_signal = raw.get("tone_signal", base["tone_signal"])
    if tone_signal not in _ALLOWED_TONE:
        issues.append("tone_signal_invalid")
        return base, issues
    base["tone_signal"] = tone_signal

    tone_markers = _coerce_str_list(raw.get("tone_marker_hits", []), max_items=10)
    base["tone_marker_hits"] = _unique_list(tone_markers, max_items=10)

    return base, issues


def normalize_belief_state(
    raw: object,
    previous: BeliefState | None = None,
) -> Tuple[BeliefState, List[str]]:
    base = default_belief_state()
    if previous:
        base.update(previous)
    issues: List[str] = []

    if not isinstance(raw, dict):
        issues.append("belief_state_no_dict")
        return base, issues

    stance = raw.get("stance", {})
    if not isinstance(stance, dict):
        issues.append("stance_invalid")
        stance = {}
    base["stance"]["deal_feasibility"] = _clamp(
        _coerce_float(stance.get("deal_feasibility", base["stance"]["deal_feasibility"]),
                      base["stance"]["deal_feasibility"])
    )
    base["stance"]["seller_flexibility"] = _clamp(
        _coerce_float(stance.get("seller_flexibility", base["stance"]["seller_flexibility"]),
                      base["stance"]["seller_flexibility"])
    )

    reasons_raw = raw.get("reasons", {})
    reasons: Dict[str, Dict[str, object]] = {}
    if isinstance(reasons_raw, dict):
        for idx, (key, value) in enumerate(reasons_raw.items()):
            if idx >= 6:
                issues.append("reasons_trimmed")
                break
            if not isinstance(value, dict):
                issues.append(f"reason_invalid:{key}")
                continue
            weight = _clamp(_coerce_float(value.get("weight", 0.5), 0.5))
            confidence = _clamp(_coerce_float(value.get("confidence", 0.5), 0.5))
            evidence = str(value.get("evidence", "")).strip()
            if not evidence:
                issues.append(f"reason_missing_evidence:{key}")
            reasons[str(key)] = {
                "weight": weight,
                "confidence": confidence,
                "evidence": evidence,
            }
    else:
        issues.append("reasons_invalid")
    base["reasons"] = reasons

    hypotheses = _coerce_str_list(raw.get("hypotheses", []), max_items=5)
    if len(hypotheses) >= 5:
        issues.append("hypotheses_trimmed")
    base["hypotheses"] = hypotheses

    dynamics = raw.get("dynamics", {})
    if not isinstance(dynamics, dict):
        issues.append("dynamics_invalid")
        dynamics = {}
    interaction_health = dynamics.get("interaction_health", base["dynamics"]["interaction_health"])
    if interaction_health not in _ALLOWED_HEALTH:
        issues.append("interaction_health_invalid")
        interaction_health = base["dynamics"]["interaction_health"]
    base["dynamics"]["interaction_health"] = interaction_health
    base["dynamics"]["last_update_evidence"] = str(
        dynamics.get("last_update_evidence", base["dynamics"]["last_update_evidence"])
    ).strip()

    tom = raw.get("tom", {})
    if not isinstance(tom, dict):
        issues.append("tom_invalid")
        tom = {}
    base["tom"]["seller_goals"] = _coerce_str_list(tom.get("seller_goals", []))
    base["tom"]["seller_tactics"] = _coerce_str_list(tom.get("seller_tactics", []))
    base["tom"]["seller_belief_about_me"] = _coerce_str_list(tom.get("seller_belief_about_me", []))
    base["tom"]["confidence"] = _clamp(
        _coerce_float(tom.get("confidence", base["tom"]["confidence"]), base["tom"]["confidence"])
    )

    return base, issues


def normalize_policy_decision(
    raw: object,
    allowed_policy_ids: Iterable[str],
) -> Tuple[PolicyDecision, List[str]]:
    base = default_policy_decision()
    issues: List[str] = []
    allowed = set(allowed_policy_ids)

    if not isinstance(raw, dict):
        issues.append("policy_decision_no_dict")
        return base, issues

    policy_id = raw.get("policy_id", base["policy_id"])
    if policy_id not in allowed:
        issues.append("policy_id_invalid")
        return base, issues
    base["policy_id"] = str(policy_id)

    base["reason"] = str(raw.get("reason", base["reason"])).strip()[:180]
    base["micro_goal"] = str(raw.get("micro_goal", base["micro_goal"])).strip()[:140]

    risk_posture = raw.get("risk_posture", base["risk_posture"])
    if risk_posture not in _ALLOWED_RISK:
        issues.append("risk_posture_invalid")
        risk_posture = base["risk_posture"]
    base["risk_posture"] = risk_posture

    return base, issues


def normalize_progress_state(raw: object) -> Tuple[ProgressState, List[str]]:
    base = default_progress_state()
    issues: List[str] = []
    if not isinstance(raw, dict):
        issues.append("progress_state_no_dict")
        return base, issues

    base["last_policy_id"] = str(raw.get("last_policy_id", base["last_policy_id"]))
    last_outcome = raw.get("last_policy_outcome", base["last_policy_outcome"])
    if last_outcome not in {"good", "neutral", "bad", ""}:
        issues.append("policy_outcome_invalid")
        last_outcome = base["last_policy_outcome"]
    base["last_policy_outcome"] = last_outcome

    attempts = raw.get("policy_attempts", {})
    if isinstance(attempts, dict):
        base["policy_attempts"] = {str(k): int(v) for k, v in attempts.items() if isinstance(v, int)}
    else:
        issues.append("policy_attempts_invalid")

    base["loop_flags"] = _unique_list(_coerce_str_list(raw.get("loop_flags", [])))
    base["turns_in_same_mode"] = int(raw.get("turns_in_same_mode", base["turns_in_same_mode"]))

    return base, issues
