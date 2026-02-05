from __future__ import annotations

import os
from typing import Any

from ..elementos.world_definitions import CONF
from ..schemas import WorldState, default_world_state


def _get_claim(
    world: WorldState,
    path: str,
    *,
    min_conf: float = 0.0,
    prefer: str = "best",
) -> dict | None:
    v2 = world.get("world_observations_v2", {}) or {}
    index = v2.get("index", {}) or {}
    table = index.get("best_by_path", {}) if prefer == "best" else index.get("latest_by_path", {})
    record = (table or {}).get(path)
    if not record:
        return None
    if float(record.get("confidence", 0.0)) < min_conf:
        return None
    return record


def _derive_legacy_from_v2(world: WorldState, confidence_min: float) -> WorldState:
    defaults = default_world_state()
    derived: dict[str, Any] = {
        "price_mentioned": False,
        "price_value": None,
        "deadline_claimed": False,
        "deadline_text": "",
        "deadline_days": None,
        "deadline_kind": "unknown",
        "urgency_claimed": False,
        "urgency_text": "",
        "urgency_reason": "",
        "other_buyer_claimed": False,
        "other_buyer_text": "",
        "other_buyer_offer_price": None,
        "other_buyer_timing_text": "",
        "concession_made": False,
        "concession_text": "",
        "batna_claimed": False,
        "batna_text": "",
        "price_firm": False,
        "price_firm_text": "",
        "evidence_offered": False,
        "evidence_text": "",
        "tone_signal": world.get("tone_signal", defaults["tone_signal"]),
        "tone_confidence": float(world.get("tone_confidence", defaults["tone_confidence"]) or 0.0),
    }

    price_offer = _get_claim(world, "negotiation.price.offer", min_conf=CONF["PRICE_NUMERIC"])
    price_mentioned = _get_claim(
        world, "negotiation.price.mentioned", min_conf=CONF["PRICE_KEYWORD"], prefer="latest"
    )
    if price_offer or price_mentioned:
        derived["price_mentioned"] = True
    if price_offer:
        derived["price_value"] = float(price_offer.get("claim", {}).get("value"))

    deadline_days = _get_claim(world, "negotiation.deadline.days", min_conf=CONF["DEADLINE_WEAK"])
    deadline_claimed = _get_claim(
        world, "negotiation.deadline.claimed", min_conf=CONF["DEADLINE_WEAK"]
    )
    if deadline_days or deadline_claimed:
        derived["deadline_claimed"] = True
        if deadline_days:
            derived["deadline_days"] = int(deadline_days.get("claim", {}).get("value") or 0)
            derived["deadline_text"] = str(deadline_days.get("provenance", {}).get("text", ""))

    urgency = _get_claim(world, "negotiation.urgency.claimed", min_conf=CONF["URGENCY_STRONG"])
    if urgency:
        derived["urgency_claimed"] = True
        derived["urgency_text"] = str(urgency.get("provenance", {}).get("text", ""))
        derived["urgency_reason"] = derived["urgency_text"][:120]

    other_buyer = _get_claim(world, "negotiation.other_buyer.claimed", min_conf=confidence_min)
    if other_buyer:
        derived["other_buyer_claimed"] = True
        derived["other_buyer_text"] = str(other_buyer.get("provenance", {}).get("text", ""))
        qualifiers = (other_buyer.get("claim", {}) or {}).get("qualifiers", {}) or {}
        derived["other_buyer_offer_price"] = qualifiers.get("offer_price")
        derived["other_buyer_timing_text"] = qualifiers.get("timing") or ""

    concession = _get_claim(world, "negotiation.concession.made", min_conf=confidence_min)
    if concession:
        derived["concession_made"] = True
        derived["concession_text"] = str(concession.get("provenance", {}).get("text", ""))

    batna = _get_claim(world, "negotiation.batna.claimed", min_conf=confidence_min)
    if batna:
        derived["batna_claimed"] = True
        derived["batna_text"] = str(batna.get("provenance", {}).get("text", ""))

    firm = _get_claim(world, "negotiation.price.firmness", min_conf=CONF["FIRMNESS_STRONG"])
    if firm:
        derived["price_firm"] = True
        derived["price_firm_text"] = str(firm.get("provenance", {}).get("text", ""))

    evidence_offer = _get_claim(world, "negotiation.evidence.offered", min_conf=confidence_min)
    if evidence_offer:
        derived["evidence_offered"] = True
        derived["evidence_text"] = str(evidence_offer.get("provenance", {}).get("text", ""))

    tone_min = float(os.getenv("CONF_TONE_MIN", "0.45"))
    tone = _get_claim(world, "negotiation.tone.signal", min_conf=tone_min)
    if tone:
        derived["tone_signal"] = str(tone.get("claim", {}).get("value", derived["tone_signal"]))
        derived["tone_confidence"] = max(
            float(derived.get("tone_confidence", 0.0)), float(tone.get("confidence", 0.0))
        )

    world.update(derived)
    world.setdefault("world_derived", {"fields": {}})
    world["world_derived"]["fields"] = dict(derived)
    return world
