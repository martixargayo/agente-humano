from __future__ import annotations

from .contracts_v2 import (
    BEHAVIOR_GUIDANCE_EPISTEMIC_STYLE,
    BEHAVIOR_GUIDANCE_RECOMMENDED_MOVES,
    clamp01,
)


def derive_behavior_guidance(belief_v2: dict, world_v2: dict) -> tuple[dict, dict]:
    uni = (belief_v2.get("universal") or {}) if isinstance(belief_v2, dict) else {}
    dynamics = (uni.get("dynamics") or {}) if isinstance(uni.get("dynamics"), dict) else {}
    metrics = (uni.get("metrics") or {}) if isinstance(uni.get("metrics"), dict) else {}
    reasons = (uni.get("reasons") or {}) if isinstance(uni.get("reasons"), dict) else {}
    neg = (belief_v2.get("negotiation") or {}) if isinstance(belief_v2, dict) else {}
    stance = (neg.get("stance") or {}) if isinstance(neg.get("stance"), dict) else {}
    world_neg2 = (world_v2.get("negotiation_v2") or {}) if isinstance(world_v2, dict) else {}

    verification_need = 0.3
    if reasons.get("evasion_signal"):
        verification_need += 0.2
    if reasons.get("clarity_signal"):
        verification_need += 0.15
    if bool((world_neg2.get("evidence") or [])):
        verification_need -= 0.1
    verification_need += 0.2 * float(stance.get("risk_level", 0.5) or 0.5)

    conflict_risk = 0.1
    if dynamics.get("interaction_health") in {"tense", "stalled"}:
        conflict_risk += 0.5
    if dynamics.get("escalation") == "up":
        conflict_risk += 0.2

    trust_estimate = float(metrics.get("trust", 0.5) or 0.5)
    assertiveness = clamp01(1.0 - conflict_risk, 0.5)
    pace_preference = clamp01(1.0 - verification_need, 0.5)

    if conflict_risk >= 0.6:
        recommended_move = "deescalate"
    elif verification_need >= 0.6:
        recommended_move = "probe"
    elif float(stance.get("deal_readiness", 0.0) or 0.0) > 0.7:
        recommended_move = "close"
    else:
        recommended_move = "hold"
    if recommended_move not in BEHAVIOR_GUIDANCE_RECOMMENDED_MOVES:
        recommended_move = "hold"

    epistemic_style = "hedged" if verification_need >= 0.6 or conflict_risk >= 0.6 else "neutral"
    if epistemic_style not in BEHAVIOR_GUIDANCE_EPISTEMIC_STYLE:
        epistemic_style = "neutral"

    guidance = {
        "assertiveness": clamp01(assertiveness, 0.5),
        "verification_need": clamp01(verification_need, 0.5),
        "trust_estimate": clamp01(trust_estimate, 0.5),
        "conflict_risk": clamp01(conflict_risk, 0.0),
        "pace_preference": clamp01(pace_preference, 0.5),
        "recommended_move": recommended_move,
        "epistemic_style": epistemic_style,
    }
    meta = {
        "governor_version": "v1",
        "drivers": {
            "interaction_health": dynamics.get("interaction_health", "stable"),
            "stance_risk_level": float(stance.get("risk_level", 0.5) or 0.5),
            "has_evasion_signal": bool(reasons.get("evasion_signal")),
            "has_evidence": bool((world_neg2.get("evidence") or [])),
        },
    }
    return guidance, meta


def summarize_epistemic_contract_from_guidance(guidance: dict) -> dict:
    verification_need = float(guidance.get("verification_need", 0.0) or 0.0)
    style = str(guidance.get("epistemic_style", "neutral") or "neutral")
    must_hedge = style == "hedged" or verification_need >= 0.6
    return {
        "epistemic_style": style,
        "must_hedge": must_hedge,
        "verify_first": verification_need >= 0.6,
        "rules": [
            "No afirmar hipótesis como hechos",
            "Usar lenguaje hedged cuando must_hedge=true",
            "Si verify_first=true, priorizar una pregunta de verificación",
        ],
    }
