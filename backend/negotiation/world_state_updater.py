# backend/negotiation/world_state_updater.py
from __future__ import annotations

import hashlib
import re
import os
from typing import Any, List, Tuple

from .evidence_registry import get_spec
from .schemas import EvidenceItem, WorldState, default_world_state
from .llm_state_extractor import (
    build_extractor_meta,
    extract_state_patch_llm,
    validate_extractor_output,
)


_PRICE_KEYWORDS = [
    "precio",
    "€",
    "euros",
    "eur",
    "pido",
    "ofrezco",
    "lo dejo",
    "último",
    "ultima",
    "última",
    "rebajo",
    "descuento",
    "negociable",
]

CONF = {
    "PRICE_NUMERIC": float(os.getenv("CONF_PRICE_NUMERIC", "0.80")),
    "PRICE_KEYWORD": float(os.getenv("CONF_PRICE_KEYWORD", "0.45")),
    "FIRMNESS_STRONG": float(os.getenv("CONF_FIRMNESS_STRONG", "0.80")),
    "FIRMNESS_WEAK": float(os.getenv("CONF_FIRMNESS_WEAK", "0.45")),
    "DEADLINE_STRONG": float(os.getenv("CONF_DEADLINE_STRONG", "0.70")),
    "DEADLINE_WEAK": float(os.getenv("CONF_DEADLINE_WEAK", "0.50")),
    "URGENCY_STRONG": float(os.getenv("CONF_URGENCY_STRONG", "0.70")),
    "URGENCY_WEAK": float(os.getenv("CONF_URGENCY_WEAK", "0.40")),
}

EVIDENCE_V2_MAX_CLAIMS = int(os.getenv("EVIDENCE_V2_MAX_CLAIMS", "200"))
EVIDENCE_V2_RECENT_K = int(os.getenv("EVIDENCE_V2_RECENT_K", "3"))
EVIDENCE_V2_MAX_UNKNOWN = int(os.getenv("EVIDENCE_V2_MAX_UNKNOWN", "50"))

_DEADLINE_PATTERNS = [
    r"\bhoy\b",
    r"\bmañana\b",
    r"\besta semana\b",
    r"\beste finde\b",
    r"\bantes de\b",
    r"\bpara el\b",
    r"\ben \d+ días\b",
    r"\ben \d+ semanas\b",
]

_TIMING_PATTERNS = [
    r"\bhoy\b",
    r"\bmañana\b",
    r"\besta semana\b",
    r"\beste finde\b",
    r"\bantes de\b",
    r"\bpara el\b",
    r"\ben \d+ días\b",
    r"\ben \d+ semanas\b",
]

_OTHER_BUYER_PATTERNS = [
    r"otro comprador",
    r"otra persona",
    r"otro interesado",
    r"hay interesados",
    r"me han ofrecido",
    r"ya tengo oferta",
]

_BATNA_PATTERNS = [
    r"tengo otro interesado",
    r"otro interesado",
    r"otro comprador",
    r"me lo quedo",
    r"me lo quedar[ée]",
    r"lo llevo a compraventa",
    r"me lo compra mi primo",
]

_URGENCY_PATTERNS_STRONG = [
    r"me urge",
    r"tengo prisa",
    r"necesito vender ya",
    r"necesito el dinero",
    r"me viene la reforma",
]

_MIN_PRICE_PATTERNS = [
    r"de\s+\d+.*no bajo",
    r"mi mínimo es",
    r"mi minimo es",
    r"no bajo de",
]

_PRICE_FIRM_PATTERNS = [
    r"precio fijo",
    r"no negociable",
    r"no negocio",
    r"precio cerrado",
]

_EVIDENCE_PATTERNS = [
    r"tengo factura",
    r"tengo informe",
    r"te enseño papeles",
    r"tengo papeles",
    r"te puedo mostrar",
]

_CONCESSION_PATTERNS = [
    r"te lo dejo",
    r"lo dejo en",
    r"último precio",
    r"ultima oferta",
    r"última oferta",
    r"puedo bajar",
    r"rebajo",
    r"descuento",
    r"me ajusto",
]

_DOCS_MAP = {
    "itv": "ITV",
    "factura": "facturas",
    "facturas": "facturas",
    "libro": "libro",
    "mantenimiento": "libro",
    "informe": "informe",
    "dgt": "DGT",
    "historial": "historial",
}

_FRIENDLY_MARKERS = ["gracias", "sin problema", "encantado", "perfecto"]
_TENSE_MARKERS = ["no tengo tiempo", "último", "ultima", "ya", "prisa", "urge"]
_CONFLICT_MARKERS = ["no pienso", "ni de broma", "no voy a", "olvídalo"]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _normalize_short(text: str) -> str:
    cleaned = re.sub(r"[^\w\s€]", "", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()[:80]


def _bucket_phrase(text: str) -> str:
    lowered = text.lower()
    if "no negociable" in lowered or "precio fijo" in lowered or "precio cerrado" in lowered:
        return "firm_strong"
    if "no negocio" in lowered:
        return "firm_weak"
    return _normalize_short(text)


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


_FIELD_TO_TYPE: dict[str, str] = {
    "price_value": "PRICE",
    "price_mentioned": "PRICE",
    "deadline_days": "DEADLINE",
    "deadline_claimed": "DEADLINE",
    "deadline_text": "DEADLINE",
    "urgency_claimed": "URGENCY",
    "urgency_reason": "URGENCY",
    "price_firm": "FIRMNESS",
    "other_buyer_claimed": "OTHER_BUYER",
    "docs_claimed": "DOCS",
    "docs_types": "DOCS",
    "batna_claimed": "BATNA",
    "min_price_claimed": "MIN_PRICE",
    "evidence_offered": "EVIDENCE_DOC",
    "concession_made": "CONCESSION",
    "tone_signal": "TONE",
}

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


def _norm_text_for_dedupe(text: str) -> str:
    return (text or "").strip().lower()[:60]


def _dedupe_key(path: str, polarity: str, bucket: Any, norm_text: str) -> str:
    raw = f"{path}|{polarity}|{bucket}|{norm_text}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _record_turn_idx(record: dict) -> int:
    return int(((record.get("provenance") or {}).get("turn_idx") or 0))


def _index_init() -> dict[str, dict]:
    return {"latest_by_path": {}, "best_by_path": {}, "recent_by_path": {}}


def _index_upsert(index: dict[str, Any], record: dict, recent_k: int) -> None:
    claim = record.get("claim", {})
    path = claim.get("path")
    if not path:
        return
    latest = index.setdefault("latest_by_path", {})
    best = index.setdefault("best_by_path", {})
    recent = index.setdefault("recent_by_path", {})
    turn_idx = _record_turn_idx(record)
    if path not in latest or turn_idx >= _record_turn_idx(latest[path]):
        latest[path] = record
    if path not in best:
        best[path] = record
    else:
        current = best[path]
        curr_conf = float(current.get("confidence", 0.0))
        next_conf = float(record.get("confidence", 0.0))
        if next_conf > curr_conf or (
            next_conf == curr_conf and turn_idx >= _record_turn_idx(current)
        ):
            best[path] = record
    recent_list = list(recent.get(path, []))
    recent_list.insert(0, record)
    recent_list.sort(key=_record_turn_idx, reverse=True)
    recent[path] = recent_list[:recent_k]


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


def _extract_sentence(text: str, match_span: tuple[int, int]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        start_idx = text.find(sentence)
        end_idx = start_idx + len(sentence)
        if start_idx <= match_span[0] <= end_idx:
            return sentence.strip()
    return text.strip()


def _extract_timing_phrase(text: str) -> str:
    match = _detect_keywords(text.lower(), _TIMING_PATTERNS)
    if not match:
        return ""
    return _extract_sentence(text, match.span())


def _parse_number(raw: str) -> float | None:
    cleaned = raw.replace(" ", "").replace("€", "")
    if not cleaned:
        return None
    if cleaned.endswith("k"):
        try:
            return float(cleaned[:-1]) * 1000
        except ValueError:
            return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _make_record_v2(
    *,
    path: str,
    value: Any,
    polarity: str,
    qualifiers: dict | None,
    confidence: float,
    text: str,
    span: tuple[int, int] | None,
    source: str,
    turn_idx: int,
    raw: dict | None,
    unknown_claims: list[dict],
) -> dict | None:
    spec = get_spec(path)
    if not spec:
        unknown_claims.append(
            {
                "path": path,
                "text": (text or "")[:120],
                "source": source,
                "turn_idx": turn_idx,
                "reason": "path_not_registered",
            }
        )
        return None
    try:
        coerced = spec.coerce(value) if value is not None else None
    except Exception:
        unknown_claims.append(
            {
                "path": path,
                "text": (text or "")[:120],
                "source": source,
                "turn_idx": turn_idx,
                "reason": "coerce_failed",
            }
        )
        return None
    qualifiers = qualifiers or {}
    if not isinstance(qualifiers, dict):
        qualifiers = {}
    cleaned_qualifiers = {k: qualifiers[k] for k in qualifiers if k in spec.qualifiers_allowed}
    bucket = spec.bucketize(coerced)
    norm_text = _norm_text_for_dedupe(text)
    return {
        "dedupe_key": _dedupe_key(path, polarity, bucket, norm_text),
        "claim": {
            "path": path,
            "value": coerced,
            "polarity": polarity or "affirm",
            "unit": spec.unit,
            "qualifiers": cleaned_qualifiers,
        },
        "confidence": float(confidence or 0.0),
        "provenance": {
            "text": text or "",
            "span": span,
            "source": source,
            "turn_idx": int(turn_idx),
            "raw": raw,
        },
    }


def _append_record_v2(
    claims: list[dict],
    record: dict,
    window_turns: int,
) -> bool:
    if not record:
        return False
    dedupe_key = record.get("dedupe_key")
    turn_idx = _record_turn_idx(record)
    for item in reversed(claims[-50:]):
        if item.get("dedupe_key") != dedupe_key:
            continue
        prev_turn = _record_turn_idx(item)
        if abs(turn_idx - prev_turn) <= window_turns:
            return False
    claims.append(record)
    return True


def _rebuild_v2_index(claims: list[dict], recent_k: int) -> dict[str, dict]:
    index = _index_init()
    for record in claims:
        _index_upsert(index, record, recent_k)
    return index


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


def _extract_price(text: str) -> float | None:
    patterns = [
        r"(\d{1,3}(?:[\.,\s]\d{3})+)(?:\s?€|\s?euros|\s?eur)?",
        r"(\d+(?:[\.,]\d+)?)(?:\s?€|\s?euros|\s?eur)",
        r"(\d+(?:[\.,]\d+)?)\s?(k|mil)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            raw = match.group(1)
            suffix = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
            value = _parse_number(raw)
            if value is None:
                continue
            if suffix.lower() in {"k", "mil"}:
                value *= 1000
            return value
    return None


def _extract_price_match(text: str) -> tuple[float | None, tuple[int, int] | None, dict | None]:
    patterns = [
        r"(\d{1,3}(?:[\.,\s]\d{3})+)(?:\s?€|\s?euros|\s?eur)?",
        r"(\d+(?:[\.,]\d+)?)(?:\s?€|\s?euros|\s?eur)",
        r"(\d+(?:[\.,]\d+)?)\s?(k|mil)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1)
        suffix = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
        value = _parse_number(raw)
        if value is None:
            continue
        if suffix.lower() in {"k", "mil"}:
            value *= 1000
        return value, match.span(), {"match": "numeric", "raw": raw}
    return None, None, None


def _detect_keywords(text: str, patterns: List[str]) -> re.Match | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _merge_list(existing: List[str], new_items: List[str]) -> List[str]:
    seen = {item.lower() for item in existing}
    merged = list(existing)
    for item in new_items:
        if item.lower() not in seen:
            merged.append(item)
            seen.add(item.lower())
    return merged


def _estimate_deadline_days(text: str) -> int | None:
    normalized = text.lower()
    if "mañana" in normalized:
        return 1
    if "hoy" in normalized:
        return 0
    if "esta semana" in normalized:
        return 7
    match = re.search(r"en (\d+) días", normalized)
    if match:
        return int(match.group(1))
    match = re.search(r"en (\d+) semanas", normalized)
    if match:
        return int(match.group(1)) * 7
    return None


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


def _dedupe_evidence(
    evidence_items: List[EvidenceItem],
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


def _append_evidence(
    evidence_items: List[EvidenceItem],
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


def _derive_tone_signal(tone_hits: List[str]) -> str:
    if not tone_hits:
        return "neutral"
    has_friendly = any(hit.startswith("friendly:") for hit in tone_hits)
    has_tense = any(hit.startswith("tense:") for hit in tone_hits)
    if has_friendly and not has_tense:
        return "friendly"
    if has_tense and not has_friendly:
        return "tense"
    return "neutral"


def _legacy_regex_update(prev_world: WorldState, user_message: str) -> WorldState:
    base = default_world_state()
    if prev_world:
        base.update(prev_world)

    text = _normalize_text(user_message)
    lower = text.lower()
    evidence_items = list(base.get("evidence_items", []))
    window_turns = int(os.getenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3"))
    turn_idx = int(base.get("world_state_meta", {}).get("turn_idx", 0) or 0)
    observed_fields: dict[str, Any] = {}

    price_value, price_span, price_raw = _extract_price_match(lower)
    has_price_context = any(keyword in lower for keyword in _PRICE_KEYWORDS)
    if price_value is not None:
        observed_fields["price_value"] = float(price_value)
        confidence = CONF["PRICE_NUMERIC"] if has_price_context else CONF["PRICE_KEYWORD"]
        _append_evidence(
            evidence_items,
            _make_evidence(
                "PRICE",
                "price_value",
                text,
                float(price_value),
                "regex",
                confidence,
                turn_idx,
                span=price_span,
                raw=price_raw,
            ),
            window_turns,
        )
    elif has_price_context:
        observed_fields["price_mentioned"] = True
        _append_evidence(
            evidence_items,
            _make_evidence(
                "PRICE",
                "price_mentioned",
                text,
                None,
                "regex",
                CONF["PRICE_KEYWORD"],
                turn_idx,
                raw={"match": "keyword"},
            ),
            window_turns,
        )

    deadline_match = _detect_keywords(lower, _DEADLINE_PATTERNS)
    if deadline_match:
        deadline_text = _extract_sentence(text, deadline_match.span())
        observed_fields["deadline_text"] = deadline_text
        observed_fields["deadline_days"] = _estimate_deadline_days(deadline_text)
        is_strong_deadline = bool(
            re.search(r"\bhoy\b|\bmañana\b|en \d+ días|en \d+ semanas", lower)
        )
        deadline_conf = CONF["DEADLINE_STRONG"] if is_strong_deadline else CONF["DEADLINE_WEAK"]
        if any(token in lower for token in ["recoger", "entregar", "entrega"]):
            observed_fields["deadline_kind"] = "pickup"
        elif any(token in lower for token in ["pagar", "pago", "pagarlo"]):
            observed_fields["deadline_kind"] = "payment"
        else:
            observed_fields["deadline_kind"] = "decision"
        _append_evidence(
            evidence_items,
            _make_evidence(
                "DEADLINE",
                "deadline_days",
                deadline_text,
                observed_fields.get("deadline_days"),
                "regex",
                deadline_conf,
                turn_idx,
                span=deadline_match.span(),
            ),
            window_turns,
        )

    other_buyer_match = _detect_keywords(lower, _OTHER_BUYER_PATTERNS)
    if other_buyer_match:
        other_buyer_text = _extract_sentence(text, other_buyer_match.span())
        observed_fields["other_buyer_text"] = other_buyer_text
        observed_fields["other_buyer_offer_price"] = _extract_price(other_buyer_text.lower())
        observed_fields["other_buyer_timing_text"] = _extract_timing_phrase(other_buyer_text)
        confidence = 0.6 if "oferta" in lower or "comprador" in lower else 0.4
        _append_evidence(
            evidence_items,
            _make_evidence(
                "OTHER_BUYER",
                "other_buyer_claimed",
                other_buyer_text,
                {
                    "offer_price": observed_fields.get("other_buyer_offer_price"),
                    "timing": observed_fields.get("other_buyer_timing_text"),
                },
                "regex",
                confidence,
                turn_idx,
                span=other_buyer_match.span(),
            ),
            window_turns,
        )

    batna_match = _detect_keywords(lower, _BATNA_PATTERNS)
    if batna_match:
        batna_text = _extract_sentence(text, batna_match.span())
        observed_fields["batna_text"] = batna_text
        _append_evidence(
            evidence_items,
            _make_evidence(
                "BATNA", "batna_claimed", batna_text, None, "regex", 0.6, turn_idx, span=batna_match.span()
            ),
            window_turns,
        )

    urgency_match = _detect_keywords(lower, _URGENCY_PATTERNS_STRONG)
    if urgency_match:
        urgency_text = _extract_sentence(text, urgency_match.span())
        observed_fields["urgency_text"] = urgency_text
        observed_fields["urgency_reason"] = urgency_text[:120]
        _append_evidence(
            evidence_items,
            _make_evidence(
                "URGENCY",
                "urgency_claimed",
                urgency_text,
                None,
                "regex",
                CONF["URGENCY_STRONG"],
                turn_idx,
                span=urgency_match.span(),
            ),
            window_turns,
        )

    min_price_match = _detect_keywords(lower, _MIN_PRICE_PATTERNS)
    if min_price_match:
        min_price_text = _extract_sentence(text, min_price_match.span())
        observed_fields["min_price_text"] = min_price_text
        _append_evidence(
            evidence_items,
            _make_evidence(
                "MIN_PRICE",
                "min_price_claimed",
                min_price_text,
                None,
                "regex",
                0.6,
                turn_idx,
                span=min_price_match.span(),
            ),
            window_turns,
        )

    price_firm_match = _detect_keywords(lower, _PRICE_FIRM_PATTERNS)
    if price_firm_match:
        price_firm_text = _extract_sentence(text, price_firm_match.span())
        observed_fields["price_firm_text"] = price_firm_text
        has_price = "precio" in price_firm_text.lower() or has_price_context
        has_strong_phrase = any(
            phrase in price_firm_text.lower()
            for phrase in ["precio fijo", "no negociable", "precio cerrado"]
        )
        confidence = CONF["FIRMNESS_STRONG"] if has_price and has_strong_phrase else CONF["FIRMNESS_WEAK"]
        _append_evidence(
            evidence_items,
            _make_evidence(
                "FIRMNESS",
                "price_firm",
                price_firm_text,
                None,
                "regex",
                confidence,
                turn_idx,
                span=price_firm_match.span(),
            ),
            window_turns,
        )

    evidence_match = _detect_keywords(lower, _EVIDENCE_PATTERNS)
    if evidence_match:
        evidence_text = _extract_sentence(text, evidence_match.span())
        observed_fields["evidence_text"] = evidence_text
        _append_evidence(
            evidence_items,
            _make_evidence(
                "EVIDENCE_DOC",
                "evidence_offered",
                evidence_text,
                None,
                "regex",
                0.6,
                turn_idx,
                span=evidence_match.span(),
            ),
            window_turns,
        )

    concession_match = _detect_keywords(lower, _CONCESSION_PATTERNS)
    if concession_match:
        concession_text = _extract_sentence(text, concession_match.span())
        observed_fields["concession_text"] = concession_text
        _append_evidence(
            evidence_items,
            _make_evidence(
                "CONCESSION",
                "concession_made",
                concession_text,
                None,
                "regex",
                0.6,
                turn_idx,
                span=concession_match.span(),
            ),
            window_turns,
        )

    docs_found: List[str] = []
    for key, label in _DOCS_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            docs_found.append(label)
    if docs_found:
        observed_fields["docs_types"] = _merge_list(base.get("docs_types", []), docs_found)
        _append_evidence(
            evidence_items,
            _make_evidence(
                "DOCS",
                "docs_claimed",
                text,
                docs_found,
                "regex",
                0.6,
                turn_idx,
            ),
            window_turns,
        )

    tone_hits: List[str] = []
    for marker in _TENSE_MARKERS:
        if marker in lower:
            tone_hits.append(f"tense:{marker}")
    for marker in _FRIENDLY_MARKERS:
        if marker in lower:
            tone_hits.append(f"friendly:{marker}")
    conflict_hits: List[str] = []
    for marker in _CONFLICT_MARKERS:
        if marker in lower:
            conflict_hits.append(marker)
    if tone_hits:
        base["tone_marker_hits"] = _merge_list(base["tone_marker_hits"], tone_hits)
    if conflict_hits:
        base["conflict_markers"] = _merge_list(base["conflict_markers"], conflict_hits)

    base["tone_signal"] = _derive_tone_signal(base.get("tone_marker_hits", []))
    base["tone_confidence"] = 0.2 if base["tone_signal"] == "neutral" else 0.6
    if tone_hits:
        _append_evidence(
            evidence_items,
            _make_evidence(
                "TONE",
                "tone_signal",
                text,
                base["tone_signal"],
                "regex",
                float(os.getenv("CONF_TONE_REGEX", "0.45")),
                turn_idx,
            ),
            window_turns,
        )
    if conflict_hits:
        _append_evidence(
            evidence_items,
            _make_evidence("TONE", "tone_signal", text, base["tone_signal"], "regex", 0.5, turn_idx),
            window_turns,
        )

    base["evidence_items"] = evidence_items
    if isinstance(base.get("world_observations"), dict):
        raw_fields = base["world_observations"].get("raw_fields", {})
        if isinstance(raw_fields, dict):
            raw_fields.update(observed_fields)
            base["world_observations"]["raw_fields"] = raw_fields
        base["world_observations"]["evidence_items"] = list(evidence_items)
    return base


def _should_call_llm_extractor(user_message: str, prev_world: WorldState) -> bool:
    text = (user_message or "").strip()
    if len(text) <= 3:
        return False
    if any(ch.isdigit() for ch in text):
        return True
    if "€" in text or "$" in text:
        return True
    if len(text) >= 40:
        return True
    if prev_world.get("other_buyer_claimed") or prev_world.get("deadline_claimed"):
        return True
    return False


def _coerce_recent_history(recent_history: list[dict] | str | None) -> list[dict]:
    if not recent_history:
        return []
    if isinstance(recent_history, str):
        txt = recent_history.strip()
        if not txt:
            return []
        return [{"role": "system", "content": txt}]
    out: list[dict] = []
    for item in recent_history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant", "system"} and isinstance(content, str) and content.strip():
            out.append({"role": role, "content": content})
    return out[-8:]


def _derive_flags_from_evidence(
    world: WorldState,
    confidence_min: float,
) -> WorldState:
    items = world.get("evidence_items", [])
    if not items:
        return world

    for item in items:
        if not item.get("field"):
            item["field"] = _infer_field(item)
        if not item.get("polarity"):
            item["polarity"] = "affirm"

    observed = world.get("world_observations", {}).get("raw_fields", {})
    defaults = default_world_state()
    tone_min = float(os.getenv("CONF_TONE_MIN", "0.45"))
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
        "docs_claimed": False,
        "docs_types": [],
        "min_price_claimed": False,
        "min_price_text": "",
        "price_firm": False,
        "price_firm_text": "",
        "evidence_offered": False,
        "evidence_text": "",
        "batna_claimed": False,
        "batna_text": "",
        "tone_signal": world.get("tone_signal", defaults["tone_signal"]),
        "tone_confidence": float(world.get("tone_confidence", defaults["tone_confidence"]) or 0.0),
    }

    def _pick_best(field: str, conf_min: float) -> EvidenceItem | None:
        candidates = [
            item
            for item in items
            if item.get("field") == field
            and float(item.get("confidence", 0.0)) >= conf_min
            and item.get("polarity", "affirm") == "affirm"
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda it: (
                float(it.get("confidence", 0.0)),
                int(it.get("turn_idx") or -1),
            ),
            reverse=True,
        )
        return candidates[0]

    best_price_value = _pick_best("price_value", CONF["PRICE_NUMERIC"])
    best_price_keyword = _pick_best("price_mentioned", CONF["PRICE_KEYWORD"])
    if best_price_value or best_price_keyword:
        derived["price_mentioned"] = True
        if best_price_value and best_price_value.get("value") is not None:
            derived["price_value"] = float(best_price_value["value"])

    best_deadline = _pick_best("deadline_days", CONF["DEADLINE_WEAK"])
    if best_deadline:
        derived["deadline_claimed"] = True
        derived["deadline_text"] = str(best_deadline.get("text", derived["deadline_text"]))
        if best_deadline.get("value") is not None:
            derived["deadline_days"] = int(best_deadline["value"])
        derived["deadline_kind"] = str(observed.get("deadline_kind", derived["deadline_kind"]))

    best_urgency = _pick_best("urgency_claimed", CONF["URGENCY_STRONG"])
    if best_urgency:
        derived["urgency_claimed"] = True
        derived["urgency_text"] = str(best_urgency.get("text", derived["urgency_text"]))
        derived["urgency_reason"] = str(best_urgency.get("text", derived["urgency_reason"]))[:120]

    best_other = _pick_best("other_buyer_claimed", confidence_min)
    if best_other:
        derived["other_buyer_claimed"] = True
        derived["other_buyer_text"] = str(best_other.get("text", derived["other_buyer_text"]))
        if isinstance(best_other.get("value"), dict):
            derived["other_buyer_offer_price"] = best_other["value"].get("offer_price")
            derived["other_buyer_timing_text"] = best_other["value"].get("timing")
        else:
            derived["other_buyer_offer_price"] = observed.get("other_buyer_offer_price")
            derived["other_buyer_timing_text"] = observed.get("other_buyer_timing_text")

    best_concession = _pick_best("concession_made", confidence_min)
    if best_concession:
        derived["concession_made"] = True
        derived["concession_text"] = str(best_concession.get("text", derived["concession_text"]))

    best_docs = _pick_best("docs_claimed", confidence_min)
    if best_docs:
        derived["docs_claimed"] = True
        if best_docs.get("value"):
            derived["docs_types"] = _merge_list(derived["docs_types"], list(best_docs["value"]))
        elif observed.get("docs_types"):
            derived["docs_types"] = _merge_list(derived["docs_types"], list(observed["docs_types"]))

    best_min_price = _pick_best("min_price_claimed", confidence_min)
    if best_min_price:
        derived["min_price_claimed"] = True
        derived["min_price_text"] = str(best_min_price.get("text", derived["min_price_text"]))

    best_firm = _pick_best("price_firm", CONF["FIRMNESS_STRONG"])
    if best_firm:
        derived["price_firm"] = True
        derived["price_firm_text"] = str(best_firm.get("text", derived["price_firm_text"]))

    best_evidence = _pick_best("evidence_offered", confidence_min)
    if best_evidence:
        derived["evidence_offered"] = True
        derived["evidence_text"] = str(best_evidence.get("text", derived["evidence_text"]))

    best_batna = _pick_best("batna_claimed", confidence_min)
    if best_batna:
        derived["batna_claimed"] = True
        derived["batna_text"] = str(best_batna.get("text", derived["batna_text"]))

    best_tone = _pick_best("tone_signal", tone_min)
    if best_tone:
        derived["tone_signal"] = str(best_tone.get("value", derived["tone_signal"]))
        derived["tone_confidence"] = max(
            float(derived.get("tone_confidence", 0.0)), float(best_tone.get("confidence", 0.0))
        )

    world.update(derived)
    world.setdefault("world_derived", {"fields": {}})
    world["world_derived"]["fields"] = dict(derived)
    world.setdefault("world_observations", {"raw_fields": {}, "evidence_items": []})
    world["world_observations"]["evidence_items"] = list(items)
    return world


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


def _build_v2_from_evidence(
    evidence_items: list[EvidenceItem],
    claims: list[dict],
    *,
    turn_idx: int,
    unknown_claims: list[dict],
) -> list[dict]:
    window_turns = int(os.getenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3"))
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        path = _path_for_legacy_item(item)
        if not path:
            unknown_claims.append(
                {
                    "path": str(item.get("field") or item.get("type") or ""),
                    "text": str(item.get("text", ""))[:120],
                    "source": item.get("source", "manual"),
                    "turn_idx": turn_idx,
                    "reason": "invalid_shape",
                }
            )
            continue
        text = str(item.get("text", "")).strip()
        confidence = item.get("confidence")
        if not text or confidence is None:
            unknown_claims.append(
                {
                    "path": path,
                    "text": text[:120],
                    "source": item.get("source", "manual"),
                    "turn_idx": turn_idx,
                    "reason": "invalid_shape",
                }
            )
            continue
        value = item.get("value")
        if path in {
            "negotiation.price.mentioned",
            "negotiation.deadline.claimed",
            "negotiation.urgency.claimed",
            "negotiation.other_buyer.claimed",
            "negotiation.concession.made",
            "negotiation.batna.claimed",
            "negotiation.evidence.offered",
        } and value is None:
            value = True
        qualifiers: dict[str, Any] = {}
        if path == "negotiation.other_buyer.claimed" and isinstance(value, dict):
            qualifiers = {
                "offer_price": value.get("offer_price"),
                "timing": value.get("timing"),
            }
            value = True
        record = _make_record_v2(
            path=path,
            value=value,
            polarity=item.get("polarity", "affirm"),
            qualifiers=qualifiers,
            confidence=float(confidence),
            text=text,
            span=item.get("span"),
            source=str(item.get("source", "manual")),
            turn_idx=turn_idx,
            raw=item.get("raw"),
            unknown_claims=unknown_claims,
        )
        if record:
            _append_record_v2(claims, record, window_turns)
    claims.sort(key=_record_turn_idx, reverse=True)
    return claims[:EVIDENCE_V2_MAX_CLAIMS]


def update_world_state(
    prev_world: WorldState | None,
    user_message: str,
    recent_history: list[dict] | str | None = None,
    belief_state: dict | None = None,
    turn_count: int | None = None,
    force_llm: bool = False,
) -> Tuple[WorldState, dict]:
    base = default_world_state()
    if prev_world:
        base.update(prev_world)

    turn_idx = int(turn_count or 0) or int((base.get("world_state_meta") or {}).get("turn_idx") or 0) + 1
    base.setdefault("world_state_meta", {})
    base["world_state_meta"]["turn_idx"] = turn_idx
    base["world_state_meta"].setdefault("unknown_claims", [])
    base.setdefault(
        "world_observations_v2",
        {"claims": [], "index": _index_init()},
    )

    recent_history = _coerce_recent_history(recent_history)
    belief_state = belief_state or {}
    use_llm = os.getenv("USE_LLM_EXTRACTOR", "true").lower() in {"1", "true", "yes"}
    use_legacy = os.getenv("USE_LEGACY_MATCHERS", "true").lower() in {"1", "true", "yes"}
    confidence_min = float(os.getenv("EVIDENCE_CONFIDENCE_MIN", "0.6"))
    base["world_state_meta"]["evidence_confidence_min"] = confidence_min

    if use_llm and (force_llm or _should_call_llm_extractor(user_message, base)):
        output = extract_state_patch_llm(base, belief_state, user_message, recent_history)
        decisions = output.get("decisions", {})
        patch = dict(output.get("world_patch", {}))
        llm_evidence = list(output.get("evidence_items", []))
        field_evidence = output.get("field_evidence", {}) or {}
        if "message_is_vague" in decisions and "message_is_vague" not in patch:
            patch["message_is_vague"] = bool(decisions.get("message_is_vague"))
        output = {**output, "world_patch": patch}
        validate_extractor_output(output)
        world = dict(base)
        for key, value in patch.items():
            world[key] = value
        generated_items: list[EvidenceItem] = []
        for field, payload in field_evidence.items():
            if not isinstance(payload, dict):
                continue
            evidence_text = str(payload.get("evidence", "")).strip()
            if not evidence_text:
                continue
            confidence = float(payload.get("confidence", confidence_min))
            evidence_type = _FIELD_TO_TYPE.get(field, "")
            if not evidence_type:
                continue
            value = patch.get(field)
            generated_items.append(
                _make_evidence(
                    evidence_type,
                    field,
                    evidence_text,
                    value,
                    "llm",
                    confidence,
                    int(base.get("world_state_meta", {}).get("turn_idx", 0) or 0),
                    raw={"field_evidence": payload},
                )
            )
        if llm_evidence or generated_items:
            window_turns = int(os.getenv("DEDUP_EVIDENCE_WINDOW_TURNS", "3"))
            items: list[EvidenceItem] = list(base.get("evidence_items", []) or [])
            for item in llm_evidence or []:
                if isinstance(item, dict):
                    _append_evidence(items, item, window_turns)
            for item in generated_items:
                _append_evidence(items, item, window_turns)
            world["evidence_items"] = items
            world["world_state_meta"]["last_update_source"] = "llm"
        meta = build_extractor_meta(output)
        unknown_claims = list(base.get("world_state_meta", {}).get("unknown_claims", []))
        claims = list((base.get("world_observations_v2") or {}).get("claims", []) or [])
        claims = _build_v2_from_evidence(
            list(world.get("evidence_items", []) or []),
            claims,
            turn_idx=turn_idx,
            unknown_claims=unknown_claims,
        )
        unknown_claims = unknown_claims[-EVIDENCE_V2_MAX_UNKNOWN:]
        world["world_state_meta"]["unknown_claims"] = unknown_claims
        world.setdefault("world_observations_v2", {"claims": [], "index": _index_init()})
        world["world_observations_v2"]["claims"] = claims
        world["world_observations_v2"]["index"] = _rebuild_v2_index(claims, EVIDENCE_V2_RECENT_K)
        world = _sync_legacy_evidence_from_v2(world)
        world = _derive_legacy_from_v2(world, confidence_min)
        world.setdefault("world_observations", {"raw_fields": {}, "evidence_items": []})
        if isinstance(world["world_observations"].get("raw_fields"), dict):
            world["world_observations"]["raw_fields"].update(patch)
        world["world_state_meta"]["updated_fields"] = sorted(
            [key for key in world.keys() if world.get(key) != base.get(key)]
        )
        return world, meta

    if use_legacy:
        world = _legacy_regex_update(base, user_message)
        world["world_state_meta"]["last_update_source"] = "regex"
        unknown_claims = list(base.get("world_state_meta", {}).get("unknown_claims", []))
        claims = list((base.get("world_observations_v2") or {}).get("claims", []) or [])
        claims = _build_v2_from_evidence(
            list(world.get("evidence_items", []) or []),
            claims,
            turn_idx=turn_idx,
            unknown_claims=unknown_claims,
        )
        unknown_claims = unknown_claims[-EVIDENCE_V2_MAX_UNKNOWN:]
        world["world_state_meta"]["unknown_claims"] = unknown_claims
        world.setdefault("world_observations_v2", {"claims": [], "index": _index_init()})
        world["world_observations_v2"]["claims"] = claims
        world["world_observations_v2"]["index"] = _rebuild_v2_index(claims, EVIDENCE_V2_RECENT_K)
        world = _sync_legacy_evidence_from_v2(world)
        world = _derive_legacy_from_v2(world, confidence_min)
        world["world_state_meta"]["updated_fields"] = sorted(
            [key for key in world.keys() if world.get(key) != base.get(key)]
        )
        return world, {
            "extractor_used": False,
            "extractor_reasons": ["legacy_fallback"],
            "extractor_world_patch_keys": [],
            "extractor_confidence_summary": {"min": 0.0, "avg": 0.0},
        }

    base["world_observations_v2"]["index"] = _rebuild_v2_index(
        list((base.get("world_observations_v2") or {}).get("claims", []) or []),
        EVIDENCE_V2_RECENT_K,
    )
    base["world_state_meta"]["unknown_claims"] = list(
        base.get("world_state_meta", {}).get("unknown_claims", [])
    )[-EVIDENCE_V2_MAX_UNKNOWN:]
    base = _sync_legacy_evidence_from_v2(base)
    base = _derive_legacy_from_v2(base, confidence_min)
    return base, {
        "extractor_used": False,
        "extractor_reasons": ["skipped"],
        "extractor_world_patch_keys": [],
        "extractor_confidence_summary": {"min": 0.0, "avg": 0.0},
    }


def diff_world_state(prev: WorldState, new: WorldState) -> dict:
    return {key: {"before": prev.get(key), "after": new.get(key)}
            for key in new.keys() if prev.get(key) != new.get(key)}
