from __future__ import annotations

import os
from typing import Any

from ..schemas import EvidenceItem, WorldState
from ..perception.interaction_signals import _normalize_short


def _bucket_phrase(text: str) -> str:
    lowered = text.lower()
    if "no negociable" in lowered or "precio fijo" in lowered or "precio cerrado" in lowered:
        return "firm_strong"
    if "no negocio" in lowered:
        return "firm_weak"
    return _normalize_short(text)


def _evidence_key(item: EvidenceItem) -> tuple:
    evidence_type = item.get("type")
    field = item.get("field") or _infer_field(item)
    polarity = item.get("polarity", "affirm")
    source = item.get("source")
    value = item.get("value")
    if evidence_type == "PRICE" and isinstance(value, (int, float)):
        return (evidence_type, field, int(round(float(value), -1)), polarity, source)
    if evidence_type == "DEADLINE":
        return (evidence_type, field, str(value), polarity, source)
    if evidence_type == "FIRMNESS":
        bucket = _bucket_phrase(item.get("text", ""))
        return (evidence_type, field, bucket, polarity, source)
    return (
        evidence_type,
        field,
        _normalize_short(item.get("text", "")),
        str(value),
        polarity,
        source,
    )


def _infer_field(item: EvidenceItem) -> str:
    if item.get("field"):
        return str(item.get("field"))
    evidence_type = item.get("type")
    if evidence_type == "PRICE":
        return "price_value" if item.get("value") is not None else "price_mentioned"
    if evidence_type == "DEADLINE":
        return "deadline_days"
    if evidence_type == "FIRMNESS":
        return "price_firm"
    if evidence_type == "URGENCY":
        return "urgency_claimed"
    if evidence_type == "OTHER_BUYER":
        return "other_buyer_claimed"
    if evidence_type == "DOCS":
        return "docs_claimed"
    if evidence_type == "BATNA":
        return "batna_claimed"
    if evidence_type == "CONCESSION":
        return "concession_made"
    if evidence_type == "MIN_PRICE":
        return "min_price_claimed"
    if evidence_type == "EVIDENCE_DOC":
        return "evidence_offered"
    if evidence_type == "TONE":
        return "tone_signal"
    return ""


def _dedupe_evidence(
    evidence_items: list[EvidenceItem],
    new_item: EvidenceItem,
    window_turns: int,
) -> bool:
    new_key = _evidence_key(new_item)
    turn_idx = new_item.get("turn_idx")
    for item in reversed(evidence_items[-50:]):
        if window_turns and turn_idx is not None and item.get("turn_idx") is not None:
            if abs(turn_idx - int(item["turn_idx"])) > window_turns:
                continue
        item_key = _evidence_key(item)
        if item_key == new_key:
            return True
    return False


def _make_evidence(
    evidence_type: str,
    field: str,
    text: str,
    value: Any,
    source: str,
    confidence: float,
    turn_idx: int | None,
    polarity: str = "affirm",
    span: tuple[int, int] | None = None,
    raw: dict | None = None,
) -> EvidenceItem:
    return {
        "type": evidence_type,
        "field": field,
        "polarity": polarity,
        "text": text.strip(),
        "value": value,
        "source": source,
        "confidence": float(confidence),
        "turn_idx": turn_idx,
        "span": span,
        "raw": raw or None,
    }


def _append_evidence(
    evidence_items: list[EvidenceItem],
    item: EvidenceItem,
    window_turns: int,
) -> None:
    if not item.get("text"):
        return
    if not item.get("field"):
        item["field"] = _infer_field(item)
    if not item.get("polarity"):
        item["polarity"] = "affirm"
    if _dedupe_evidence(evidence_items, item, window_turns):
        return
    evidence_items.append(item)


LEGACY_FIELD_TO_PATH: dict[str, str] = {
    "price_value": "negotiation.price.offer",
    "price_mentioned": "negotiation.price.mentioned",
    "price_firm": "negotiation.price.firmness",
    "deadline_days": "negotiation.deadline.days",
    "deadline_claimed": "negotiation.deadline.claimed",
    "urgency_claimed": "negotiation.urgency.claimed",
    "other_buyer_claimed": "negotiation.other_buyer.claimed",
    "concession_made": "negotiation.concession.made",
    "batna_claimed": "negotiation.batna.claimed",
    "tone_signal": "negotiation.tone.signal",
    "evidence_offered": "negotiation.evidence.offered",
}

PATH_TO_LEGACY: dict[str, dict[str, str]] = {
    "negotiation.price.offer": {"type": "PRICE", "field": "price_value"},
    "negotiation.price.mentioned": {"type": "PRICE", "field": "price_mentioned"},
    "negotiation.price.firmness": {"type": "FIRMNESS", "field": "price_firm"},
    "negotiation.deadline.days": {"type": "DEADLINE", "field": "deadline_days"},
    "negotiation.deadline.claimed": {"type": "DEADLINE", "field": "deadline_claimed"},
    "negotiation.urgency.claimed": {"type": "URGENCY", "field": "urgency_claimed"},
    "negotiation.other_buyer.claimed": {"type": "OTHER_BUYER", "field": "other_buyer_claimed"},
    "negotiation.concession.made": {"type": "CONCESSION", "field": "concession_made"},
    "negotiation.batna.claimed": {"type": "BATNA", "field": "batna_claimed"},
    "negotiation.tone.signal": {"type": "TONE", "field": "tone_signal"},
    "negotiation.evidence.offered": {"type": "EVIDENCE_DOC", "field": "evidence_offered"},
}


def _path_for_legacy_item(item: EvidenceItem) -> str | None:
    raw_path = (item.get("raw") or {}).get("path")
    if isinstance(raw_path, str) and raw_path:
        return raw_path
    field = item.get("field") or ""
    if isinstance(field, str) and "." in field:
        return field
    field = _infer_field(item)
    if field in LEGACY_FIELD_TO_PATH:
        return LEGACY_FIELD_TO_PATH[field]
    evidence_type = item.get("type")
    if evidence_type == "PRICE":
        if item.get("value") is not None:
            return "negotiation.price.offer"
        return "negotiation.price.mentioned"
    if evidence_type == "DEADLINE":
        return "negotiation.deadline.days"
    if evidence_type == "FIRMNESS":
        return "negotiation.price.firmness"
    if evidence_type == "URGENCY":
        return "negotiation.urgency.claimed"
    if evidence_type == "OTHER_BUYER":
        return "negotiation.other_buyer.claimed"
    if evidence_type == "CONCESSION":
        return "negotiation.concession.made"
    if evidence_type == "BATNA":
        return "negotiation.batna.claimed"
    if evidence_type == "TONE":
        return "negotiation.tone.signal"
    if evidence_type == "EVIDENCE_DOC":
        return "negotiation.evidence.offered"
    return None


def _v2_record_to_legacy_item(record: dict) -> EvidenceItem | None:
    claim = record.get("claim", {})
    path = claim.get("path")
    mapping = PATH_TO_LEGACY.get(path or "")
    if not mapping:
        return None
    provenance = record.get("provenance", {})
    return _make_evidence(
        mapping["type"],
        mapping["field"],
        str(provenance.get("text", "")),
        claim.get("value"),
        str(provenance.get("source", "manual")),
        float(record.get("confidence", 0.0)),
        int(provenance.get("turn_idx") or 0),
        span=provenance.get("span"),
        raw={"v2_path": path, "qualifiers": claim.get("qualifiers", {})},
    )


def _sync_legacy_evidence_from_v2(world: WorldState) -> WorldState:
    claims = (world.get("world_observations_v2") or {}).get("claims", []) or []
    items: list[EvidenceItem] = []
    window_turns = int(os.getenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3"))
    for record in claims:
        legacy = _v2_record_to_legacy_item(record)
        if legacy:
            _append_evidence(items, legacy, window_turns)
    world["evidence_items"] = items
    world.setdefault("world_observations", {"raw_fields": {}, "evidence_items": []})
    world["world_observations"]["evidence_items"] = list(items)
    return world
