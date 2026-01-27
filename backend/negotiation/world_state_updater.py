# backend/negotiation/world_state_updater.py
from __future__ import annotations

import re
import os
from typing import List, Tuple

from .schemas import WorldState, default_world_state
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

_URGENCY_PATTERNS = [
    r"lo necesito",
    r"me urge",
    r"me urge",
    r"me viene la reforma",
    r"esta semana",
    r"antes del",
    r"antes de",
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
        base["other_buyer_text"] = _extract_sentence(text, other_buyer_match.span())
        base["other_buyer_offer_price"] = _extract_price(base["other_buyer_text"].lower())
        base["other_buyer_timing_text"] = _extract_timing_phrase(base["other_buyer_text"])

    batna_match = _detect_keywords(lower, _BATNA_PATTERNS)
    if batna_match:
        base["batna_claimed"] = True
        base["batna_text"] = _extract_sentence(text, batna_match.span())

    urgency_match = _detect_keywords(lower, _URGENCY_PATTERNS)
    if urgency_match:
        base["urgency_claimed"] = True
        base["urgency_text"] = _extract_sentence(text, urgency_match.span())

    min_price_match = _detect_keywords(lower, _MIN_PRICE_PATTERNS)
    if min_price_match:
        base["min_price_claimed"] = True
        base["min_price_text"] = _extract_sentence(text, min_price_match.span())

    price_firm_match = _detect_keywords(lower, _PRICE_FIRM_PATTERNS)
    if price_firm_match:
        base["price_firm"] = True
        base["price_firm_text"] = _extract_sentence(text, price_firm_match.span())

    evidence_match = _detect_keywords(lower, _EVIDENCE_PATTERNS)
    if evidence_match:
        base["evidence_offered"] = True
        base["evidence_text"] = _extract_sentence(text, evidence_match.span())

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

    base["tone_signal"] = _derive_tone_signal(base.get("tone_marker_hits", []))

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


def update_world_state(
    prev_world: WorldState | None,
    user_message: str,
    recent_history: list[dict] | str | None = None,
    belief_state: dict | None = None,
) -> Tuple[WorldState, dict]:
    base = default_world_state()
    if prev_world:
        base.update(prev_world)

    recent_history = _coerce_recent_history(recent_history)
    belief_state = belief_state or {}
    use_llm = os.getenv("USE_LLM_EXTRACTOR", "true").lower() in {"1", "true", "yes"}
    use_legacy = os.getenv("USE_LEGACY_MATCHERS", "true").lower() in {"1", "true", "yes"}

    if use_llm and _should_call_llm_extractor(user_message, base):
        output = extract_state_patch_llm(base, belief_state, user_message, recent_history)
        decisions = output.get("decisions", {})
        patch = dict(output.get("world_patch", {}))
        if "message_is_vague" in decisions and "message_is_vague" not in patch:
            patch["message_is_vague"] = bool(decisions.get("message_is_vague"))
        output = {**output, "world_patch": patch}
        validate_extractor_output(output)
        world = dict(base)
        for key, value in patch.items():
            world[key] = value
        meta = build_extractor_meta(output)
        return world, meta

    if use_legacy:
        world = _legacy_regex_update(base, user_message)
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
