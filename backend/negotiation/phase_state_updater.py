# backend/negotiation/phase_state_updater.py
from __future__ import annotations

from .schemas import NegotiationPhase, PhaseState, default_progress_state
from .validation import normalize_phase_state


_PHASE_ORDER: list[NegotiationPhase] = ["opening", "discovery", "bargaining", "closing"]
_PHASE_INDEX = {phase: idx for idx, phase in enumerate(_PHASE_ORDER)}


def _transition_threshold(prev: NegotiationPhase, new: NegotiationPhase) -> float:
    if prev == new:
        return 0.0
    if prev == "recovery" or new == "recovery":
        return 0.55
    if prev in _PHASE_INDEX and new in _PHASE_INDEX:
        dist = abs(_PHASE_INDEX[new] - _PHASE_INDEX[prev])
        return 0.62 if dist == 1 else 0.72
    return 0.70


def _apply_hysteresis(
    prev_state: PhaseState,
    proposed: dict,
    turn_count: int,
) -> tuple[PhaseState, dict]:
    prev_phase: NegotiationPhase = prev_state.get("phase", "opening")
    prev_conf = float(prev_state.get("confidence", 0.6) or 0.6)
    new_phase = proposed.get("phase", prev_phase)
    new_conf = float(proposed.get("confidence", prev_conf) or prev_conf)

    threshold = _transition_threshold(prev_phase, new_phase)
    meta = {
        "threshold": threshold,
        "attempted_change": new_phase != prev_phase,
        "held": False,
    }
    if new_phase != prev_phase and new_conf < threshold:
        proposed["phase"] = prev_phase
        proposed["confidence"] = max(prev_conf, new_conf) * 0.97
        reasons = list(proposed.get("reasons") or [])
        proposed["reasons"] = (["history:hysteresis_hold"] + reasons)[:8]
        meta["held"] = True

    proposed["last_updated_turn"] = turn_count
    normalized, _ = normalize_phase_state(proposed)
    return normalized, meta


def _sync_phase_meta(meta: dict, normalized: PhaseState) -> None:
    meta["phase_after"] = normalized.get("phase", "opening")
    meta["phase_confidence_after"] = float(normalized.get("confidence", 0.6) or 0.6)
    meta["phase_changed"] = meta.get("phase_before") != meta["phase_after"]


def postprocess_phase_candidate(
    prev_phase_state: PhaseState | None,
    phase_candidate: dict,
    turn_count: int,
) -> tuple[PhaseState, dict]:
    prev = prev_phase_state or default_progress_state()["phase_state"]
    meta = {
        "phase_update_used": True,
        "phase_update_reason": "planner",
        "phase_update_failed": False,
        "phase_changed": False,
        "phase_before": prev.get("phase", "opening"),
        "phase_after": prev.get("phase", "opening"),
        "phase_confidence_before": float(prev.get("confidence", 0.6) or 0.6),
        "phase_confidence_after": float(prev.get("confidence", 0.6) or 0.6),
        "phase_hard_override_used": False,
        "phase_llm_confidence": float(phase_candidate.get("confidence", 0.0) or 0.0),
        "phase_llm_phase_proposed": phase_candidate.get("phase"),
        "phase_transition_attempted": False,
        "phase_threshold_used": None,
        "phase_hysteresis_held": False,
    }
    normalized, hyst = _apply_hysteresis(prev, phase_candidate, turn_count)
    meta["phase_threshold_used"] = hyst["threshold"]
    meta["phase_transition_attempted"] = hyst["attempted_change"]
    meta["phase_hysteresis_held"] = hyst["held"]
    _sync_phase_meta(meta, normalized)
    return normalized, meta
