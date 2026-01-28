# backend/negotiation/world_state_updater.py
from __future__ import annotations

import re
import os
from typing import Any, List, Tuple

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


def update_world_state(
    prev_world: WorldState | None,
    user_message: str,
    recent_history: list[dict] | str | None = None,
    belief_state: dict | None = None,
    turn_count: int | None = None,
) -> Tuple[WorldState, dict]:
    base = default_world_state()
    if prev_world:
        base.update(prev_world)

    recent_history = _coerce_recent_history(recent_history)
    belief_state = belief_state or {}
    use_llm = os.getenv("USE_LLM_EXTRACTOR", "true").lower() in {"1", "true", "yes"}
    use_legacy = os.getenv("USE_LEGACY_MATCHERS", "true").lower() in {"1", "true", "yes"}
    confidence_min = float(os.getenv("EVIDENCE_CONFIDENCE_MIN", "0.6"))
    base["world_state_meta"]["evidence_confidence_min"] = confidence_min
    if turn_count is not None:
        base["world_state_meta"]["turn_idx"] = int(turn_count)

    if use_llm and _should_call_llm_extractor(user_message, base):
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
        world = _derive_flags_from_evidence(world, confidence_min)
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
        world = _derive_flags_from_evidence(world, confidence_min)
        world["world_state_meta"]["updated_fields"] = sorted(
            [key for key in world.keys() if world.get(key) != base.get(key)]
        )
        return world, {
            "extractor_used": False,
            "extractor_reasons": ["legacy_fallback"],
            "extractor_world_patch_keys": [],
            "extractor_confidence_summary": {"min": 0.0, "avg": 0.0},
        }

    return base, {
        "extractor_used": False,
        "extractor_reasons": ["skipped"],
        "extractor_world_patch_keys": [],
        "extractor_confidence_summary": {"min": 0.0, "avg": 0.0},
    }


def diff_world_state(prev: WorldState, new: WorldState) -> dict:
    return {key: {"before": prev.get(key), "after": new.get(key)}
            for key in new.keys() if prev.get(key) != new.get(key)}
