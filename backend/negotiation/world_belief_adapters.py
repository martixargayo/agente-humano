from __future__ import annotations

from typing import Any


def world_v1_to_v2(world_v1: dict | None) -> dict:
    w = dict(world_v1 or {})
    u = w.get("universal_domain", {}) if isinstance(w.get("universal_domain"), dict) else {}
    n = w.get("negotiation", {}) if isinstance(w.get("negotiation"), dict) else {}
    universal_v2 = {
        "clarity": {
            "is_vague": bool(u.get("message_is_vague", False)),
            "missing_info": [],
            "ambiguity_types": [],
            "confidence": float(u.get("tone_confidence", 0.0) or 0.0),
        },
        "affect": {
            "tone": str(u.get("tone_signal", "neutral") or "neutral"),
            "confidence": float(u.get("tone_confidence", 0.0) or 0.0),
            "sentiment": "neutral",
            "arousal": "medium",
        },
        "interaction": {
            "cooperation": 0.5,
            "friction": 0.0,
            "boundary": False,
            "loop": False,
            "commitment_signal": 0.0,
        },
        "intent": {"act": "inform", "confidence": 0.0},
        "commitments": [],
    }
    evidence = []
    if n.get("docs_claimed") or n.get("evidence_offered"):
        evidence.append(
            {
                "type": "doc",
                "items": list(n.get("docs_types", [])) if isinstance(n.get("docs_types"), list) else [],
                "text": str(n.get("evidence_text") or n.get("docs_text") or ""),
                "status": "claimed",
                "confidence": 0.6,
                "meta": {},
            }
        )
    leverage_claims = []
    if n.get("other_buyer_claimed"):
        leverage_claims.append(
            {
                "side": "seller",
                "type": "other_buyer",
                "text": str(n.get("other_buyer_text", "")),
                "value": n.get("other_buyer_offer_price"),
                "evidence_ref": None,
                "status": "claimed",
                "confidence": 0.6,
            }
        )
    offers = []
    if n.get("price_mentioned"):
        offers.append(
            {
                "side": "seller",
                "kind": "price",
                "value": {"amount": n.get("price_value"), "currency": "EUR"} if n.get("price_value") is not None else None,
                "terms": [],
                "text": str(n.get("price_firm_text") or ""),
                "firmness": "hard" if n.get("price_firm") else "medium",
                "status": "active",
                "confidence": 0.7,
            }
        )
    constraints = []
    if n.get("min_price_claimed"):
        constraints.append(
            {
                "side": "seller",
                "kind": "min",
                "dimension": "price",
                "value": n.get("min_price_text"),
                "text": str(n.get("min_price_text", "")),
                "flexibility": 0.2,
                "status": "claimed",
                "confidence": 0.6,
            }
        )
    negotiation_v2 = {
        "subject": {"item": "", "context": "", "attributes": {}},
        "offers": offers,
        "constraints": constraints,
        "interests": [],
        "concessions": [],
        "time_pressure": {
            "deadline_text": str(n.get("deadline_text", "")),
            "deadline_date": None,
            "window_days": n.get("deadline_days"),
            "urgency": 0.7 if n.get("urgency_claimed") else 0.0,
            "reason": str(n.get("urgency_reason", "")),
            "status": "claimed" if (n.get("deadline_claimed") or n.get("urgency_claimed")) else "unverified",
            "confidence": 0.6 if (n.get("deadline_claimed") or n.get("urgency_claimed")) else 0.0,
        },
        "leverage_claims": leverage_claims,
        "evidence": evidence,
        "agreement_state": {"state": "none", "next_step": "", "open_points": [], "confidence": 0.0},
    }
    w["schema_version"] = "v2"
    w["universal_v2"] = universal_v2
    w["negotiation_v2"] = negotiation_v2
    return w


def belief_v1_to_v2(belief_v1: dict | None) -> dict:
    b = dict(belief_v1 or {})
    b["schema_version"] = "v2"
    uni = b.get("universal", {}) if isinstance(b.get("universal"), dict) else {}
    tom = uni.get("tom", {}) if isinstance(uni.get("tom"), dict) else {}
    tom.setdefault("hypotheses", [])
    uni["tom"] = tom
    uni.setdefault(
        "behavior_guidance",
        {
            "assertiveness": 0.5,
            "verification_need": 0.5,
            "trust_estimate": 0.5,
            "conflict_risk": 0.0,
            "pace_preference": 0.5,
            "recommended_move": "hold",
            "epistemic_style": "neutral",
        },
    )
    b["universal"] = uni
    return b
