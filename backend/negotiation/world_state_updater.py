# backend/negotiation/world_state_updater.py
from __future__ import annotations

import re
from typing import List

from .schemas import WorldState, default_world_state


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
]

_DEADLINE_PATTERNS = [
    r"\bhoy\b",
    r"\bmañana\b",
    r"\besta semana\b",
    r"\beste finde\b",
    r"\bantes de\b",
    r"\bme urge\b",
    r"\burg(e|encia)\b",
    r"\bprisa\b",
    r"\bya\b",
]

_OTHER_BUYER_PATTERNS = [
    r"otro comprador",
    r"otra persona",
    r"otro interesado",
    r"hay interesados",
    r"me han ofrecido",
    r"ya tengo oferta",
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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _extract_sentence(text: str, match_span: tuple[int, int]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        start_idx = text.find(sentence)
        end_idx = start_idx + len(sentence)
        if start_idx <= match_span[0] <= end_idx:
            return sentence.strip()
    return text.strip()


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


def update_world_state(prev_world: WorldState | None, user_message: str) -> WorldState:
    base = default_world_state()
    if prev_world:
        base.update(prev_world)
    base.pop("tone_signal", None)

    text = _normalize_text(user_message)
    lower = text.lower()

    price_value = _extract_price(lower)
    if price_value is not None:
        base["price_mentioned"] = True
        base["price_value"] = float(price_value)
    elif any(keyword in lower for keyword in _PRICE_KEYWORDS):
        base["price_mentioned"] = True

    deadline_match = _detect_keywords(lower, _DEADLINE_PATTERNS)
    if deadline_match:
        base["deadline_claimed"] = True
        base["deadline_text"] = _extract_sentence(text, deadline_match.span())

    other_buyer_match = _detect_keywords(lower, _OTHER_BUYER_PATTERNS)
    if other_buyer_match:
        base["other_buyer_claimed"] = True

    concession_match = _detect_keywords(lower, _CONCESSION_PATTERNS)
    if concession_match:
        base["concession_made"] = True
        base["concession_text"] = _extract_sentence(text, concession_match.span())

    docs_found: List[str] = []
    for key, label in _DOCS_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            docs_found.append(label)
    if docs_found:
        base["docs_claimed"] = True
        base["docs_types"] = _merge_list(base["docs_types"], docs_found)

    tone_hits: List[str] = []
    for marker in _TENSE_MARKERS:
        if marker in lower:
            tone_hits.append(f"tense:{marker}")
    for marker in _FRIENDLY_MARKERS:
        if marker in lower:
            tone_hits.append(f"friendly:{marker}")
    if tone_hits:
        base["tone_marker_hits"] = _merge_list(base["tone_marker_hits"], tone_hits)

    return base


def diff_world_state(prev: WorldState, new: WorldState) -> dict:
    return {key: {"before": prev.get(key), "after": new.get(key)}
            for key in new.keys() if prev.get(key) != new.get(key)}
