# backend/negotiation/phase_state_updater.py
from __future__ import annotations

from .phase_migration import normalize_phase_candidate
from .schemas import NegotiationPhase, PhaseState, default_progress_state
from .perception.clarity_signals import compute_clarity_signals
from .validation import normalize_phase_state

_PHASE_ORDER: list[NegotiationPhase] = ["climate", "interests", "options", "adjust", "formalize"]
_PHASE_INDEX = {phase: idx for idx, phase in enumerate(_PHASE_ORDER)}


def _transition_threshold(prev: NegotiationPhase, new: NegotiationPhase) -> float:
    if prev == new:
        return 0.0
    if prev in _PHASE_INDEX and new in _PHASE_INDEX:
        dist = abs(_PHASE_INDEX[new] - _PHASE_INDEX[prev])
        return 0.62 if dist == 1 else 0.72
    return 0.70


def _nested_get(data: dict, *path: str):
    cur: object = data
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _len_value(value: object) -> int:
    if isinstance(value, (list, dict, tuple, set)):
        return len(value)
    return 0


def _compute_recovery_mode(prev: PhaseState, world_state: dict, belief_state: dict, progress_state: dict | None) -> tuple[bool, int]:
    health = str(_nested_get(belief_state, "planner_signals", "interaction_health") or "stable")
    conflict_risk = float(_nested_get(belief_state, "planner_signals", "conflict_risk") or 0.0)
    loop_flags = list((progress_state or {}).get("loop_flags", [])) if isinstance(progress_state, dict) else []
    has_loop = bool(loop_flags)

    recovery_on = health in {"tense", "stalled"} or conflict_risk >= 0.6 or has_loop
    prev_stable_turns = int(prev.get("recovery_stable_turns", 0) or 0)
    if health == "stable" and conflict_risk < 0.5 and not has_loop:
        stable_turns = prev_stable_turns + 1
    else:
        stable_turns = 0

    if recovery_on:
        return True, 0
    if bool(prev.get("recovery_mode", False)) and stable_turns < 2:
        return True, stable_turns
    return False, stable_turns


def _gate_effective_phase(base_phase: NegotiationPhase, world_state: dict, belief_state: dict, turn_count: int, recovery_mode: bool) -> NegotiationPhase:
    if recovery_mode:
        return "climate"

    buckets = (world_state or {}).get("world_buckets", {}) if isinstance(world_state, dict) else {}
    interests_n = _len_value(buckets.get("interests", [])) if isinstance(buckets, dict) else 0
    constraints_n = _len_value(buckets.get("constraints", [])) if isinstance(buckets, dict) else 0
    offers_n = _len_value(buckets.get("offers", [])) if isinstance(buckets, dict) else 0
    claims_n = _len_value(buckets.get("claims", [])) if isinstance(buckets, dict) else 0
    if claims_n >= 3 and interests_n == 0:
        return "interests"

    clarity_vague = bool(compute_clarity_signals(world_state, belief_state).get("clarity_vague", False))

    phase = base_phase
    affect_conf = 0.5 if claims_n > 0 else 0.0
    agree_state = "near" if offers_n > 1 and constraints_n > 0 else "none"
    agree_conf = 0.7 if agree_state == "near" else 0.0

    if phase == "climate":
        if affect_conf >= 0.3 or (turn_count >= 1 and not clarity_vague):
            return "interests"
        return "climate"
    if phase == "interests":
        if (interests_n >= 1 or constraints_n >= 1) and not clarity_vague:
            return "options"
        return "interests"
    if phase == "options":
        if offers_n > 0 or agree_conf >= 0.4:
            return "adjust"
        return "options"
    if phase == "adjust":
        if agree_state in {"near", "agreed"} or agree_conf >= 0.7:
            return "formalize"
        return "adjust"
    return phase


def _apply_hysteresis(
    prev_state: PhaseState,
    proposed: dict,
    turn_count: int,
) -> tuple[PhaseState, dict]:
    prev_phase: NegotiationPhase = prev_state.get("phase_effective") or prev_state.get("phase", "climate")
    prev_conf = float(prev_state.get("confidence", 0.6) or 0.6)
    new_phase = proposed.get("phase_effective", proposed.get("phase", prev_phase))
    new_conf = float(proposed.get("confidence", prev_conf) or prev_conf)

    threshold = _transition_threshold(prev_phase, new_phase)
    meta = {
        "threshold": threshold,
        "attempted_change": new_phase != prev_phase,
        "held": False,
    }
    if new_phase != prev_phase and new_conf < threshold:
        proposed["phase_effective"] = prev_phase
        proposed["phase"] = proposed.get("phase", prev_phase)
        proposed["confidence"] = max(prev_conf, new_conf) * 0.97
        reasons = list(proposed.get("reasons") or [])
        proposed["reasons"] = (["history:hysteresis_hold"] + reasons)[:8]
        meta["held"] = True

    proposed["last_updated_turn"] = turn_count
    normalized, _ = normalize_phase_state(proposed)
    return normalized, meta


def _sync_phase_meta(meta: dict, normalized: PhaseState) -> None:
    meta["phase_after"] = normalized.get("phase_effective", normalized.get("phase", "climate"))
    meta["phase_confidence_after"] = float(normalized.get("confidence", 0.6) or 0.6)
    meta["phase_changed"] = meta.get("phase_before") != meta["phase_after"]


def postprocess_phase_candidate(
    prev_phase_state: PhaseState | None,
    phase_candidate: dict,
    turn_count: int,
    world_state: dict | None = None,
    belief_state: dict | None = None,
    progress_state: dict | None = None,
) -> tuple[PhaseState, dict]:
    prev = prev_phase_state or default_progress_state()["phase_state"]
    raw_phase = str(phase_candidate.get("phase", "")).strip().lower()
    normalized_phase, proposed_raw, mapped_recovery, migration_issues = normalize_phase_candidate(
        raw_phase,
        bool(phase_candidate.get("recovery_mode", False)),
    )
    world_state = world_state or {}
    belief_state = belief_state or {}

    recovery_mode, stable_turns = _compute_recovery_mode(prev, world_state, belief_state, progress_state)
    recovery_mode = bool(recovery_mode or mapped_recovery)
    effective_phase = _gate_effective_phase(normalized_phase, world_state, belief_state, turn_count, recovery_mode)

    merged = {
        "phase": normalized_phase,
        "phase_proposed": proposed_raw,
        "phase_effective": effective_phase,
        "recovery_mode": recovery_mode,
        "recovery_stable_turns": stable_turns,
        "confidence": float(phase_candidate.get("confidence", 0.0) or 0.0),
        "reasons": list(phase_candidate.get("reasons", [])),
        "last_updated_turn": turn_count,
    }

    meta = {
        "phase_update_used": True,
        "phase_update_reason": "planner",
        "phase_update_failed": False,
        "phase_changed": False,
        "phase_before": prev.get("phase_effective") or prev.get("phase", "climate"),
        "phase_after": prev.get("phase_effective") or prev.get("phase", "climate"),
        "phase_confidence_before": float(prev.get("confidence", 0.6) or 0.6),
        "phase_confidence_after": float(prev.get("confidence", 0.6) or 0.6),
        "phase_hard_override_used": False,
        "phase_llm_confidence": float(phase_candidate.get("confidence", 0.0) or 0.0),
        "phase_llm_phase_proposed": phase_candidate.get("phase"),
        "phase_transition_attempted": False,
        "phase_threshold_used": None,
        "phase_hysteresis_held": False,
        "phase_migration_issues": migration_issues,
        "recovery_mode": recovery_mode,
    }

    normalized, hyst = _apply_hysteresis(prev, merged, turn_count)
    meta["phase_threshold_used"] = hyst["threshold"]
    meta["phase_transition_attempted"] = hyst["attempted_change"]
    meta["phase_hysteresis_held"] = hyst["held"]
    _sync_phase_meta(meta, normalized)
    return normalized, meta
