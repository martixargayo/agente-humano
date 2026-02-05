from __future__ import annotations

import os
import re
from typing import Any, List

from ..elementos.world_definitions import (
    BATNA_PATTERNS,
    CONCESSION_PATTERNS,
    CONF,
    DEADLINE_PATTERNS,
    DOCS_MAP,
    EVIDENCE_PATTERNS,
    CONFLICT_MARKERS,
    FRIENDLY_MARKERS,
    MIN_PRICE_PATTERNS,
    OTHER_BUYER_PATTERNS,
    PRICE_FIRM_PATTERNS,
    PRICE_KEYWORDS,
    TIMING_PATTERNS,
    TENSE_MARKERS,
    URGENCY_PATTERNS_STRONG,
)
from ..evidence.legacy_bridge import _append_evidence, _make_evidence
from ..perception.interaction_signals import _derive_tone_signal, _normalize_text
from ..schemas import WorldState, default_world_state


def _merge_list(existing: List[str], new_items: List[str]) -> List[str]:
    seen = {item.lower() for item in existing}
    merged = list(existing)
    for item in new_items:
        if item.lower() not in seen:
            merged.append(item)
            seen.add(item.lower())
    return merged


def _extract_sentence(text: str, match_span: tuple[int, int]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        start_idx = text.find(sentence)
        end_idx = start_idx + len(sentence)
        if start_idx <= match_span[0] <= end_idx:
            return sentence.strip()
    return text.strip()


def _detect_keywords(text: str, patterns: List[str]) -> re.Match | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _extract_timing_phrase(text: str) -> str:
    match = _detect_keywords(text.lower(), TIMING_PATTERNS)
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
    has_price_context = any(keyword in lower for keyword in PRICE_KEYWORDS)
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

    deadline_match = _detect_keywords(lower, DEADLINE_PATTERNS)
    if deadline_match:
        deadline_text = _extract_sentence(text, deadline_match.span())
        observed_fields["deadline_text"] = deadline_text
        observed_fields["deadline_days"] = _estimate_deadline_days(deadline_text)
        is_strong_deadline = bool(
            re.search(r"\\bhoy\\b|\\bmañana\\b|en \\d+ días|en \\d+ semanas", lower)
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

    other_buyer_match = _detect_keywords(lower, OTHER_BUYER_PATTERNS)
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

    batna_match = _detect_keywords(lower, BATNA_PATTERNS)
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

    urgency_match = _detect_keywords(lower, URGENCY_PATTERNS_STRONG)
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

    min_price_match = _detect_keywords(lower, MIN_PRICE_PATTERNS)
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

    price_firm_match = _detect_keywords(lower, PRICE_FIRM_PATTERNS)
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

    evidence_match = _detect_keywords(lower, EVIDENCE_PATTERNS)
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

    concession_match = _detect_keywords(lower, CONCESSION_PATTERNS)
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
    for key, label in DOCS_MAP.items():
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
    for marker in TENSE_MARKERS:
        if marker in lower:
            tone_hits.append(f"tense:{marker}")
    for marker in FRIENDLY_MARKERS:
        if marker in lower:
            tone_hits.append(f"friendly:{marker}")
    conflict_hits: List[str] = []
    for marker in CONFLICT_MARKERS:
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
