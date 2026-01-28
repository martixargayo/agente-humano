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
_CONFLICT_MARKERS = ["no pienso", "ni de broma", "no voy a", "olvídalo"]


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
    text: str,
    value: Any,
    source: str,
    confidence: float,
    turn_idx: int | None,
    raw: dict | None = None,
) -> EvidenceItem:
    return {
        "type": evidence_type,
        "text": text.strip(),
        "value": value,
        "source": source,
        "confidence": float(confidence),
        "turn_idx": turn_idx,
        "raw": raw or None,
    }


def _dedupe_evidence(
    evidence_items: List[EvidenceItem],
    new_item: EvidenceItem,
    window_turns: int,
) -> bool:
    new_key = (
        new_item.get("type"),
        (new_item.get("text") or "").lower(),
        str(new_item.get("value")),
        new_item.get("source"),
    )
    turn_idx = new_item.get("turn_idx")
    for item in reversed(evidence_items[-50:]):
        if window_turns and turn_idx is not None and item.get("turn_idx") is not None:
            if abs(turn_idx - int(item["turn_idx"])) > window_turns:
                continue
        item_key = (
            item.get("type"),
            (item.get("text") or "").lower(),
            str(item.get("value")),
            item.get("source"),
        )
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

    price_value = _extract_price(lower)
    if price_value is not None:
        base["price_mentioned"] = True
        base["price_value"] = float(price_value)
        confidence = 0.8 if any(keyword in lower for keyword in _PRICE_KEYWORDS) else 0.6
        _append_evidence(
            evidence_items,
            _make_evidence(
                "PRICE",
                text,
                float(price_value),
                "regex",
                confidence,
                turn_idx,
                raw={"match": "numeric"},
            ),
            window_turns,
        )
    elif any(keyword in lower for keyword in _PRICE_KEYWORDS):
        base["price_mentioned"] = True
        _append_evidence(
            evidence_items,
            _make_evidence("PRICE", text, None, "regex", 0.4, turn_idx, raw={"match": "keyword"}),
            window_turns,
        )

    deadline_match = _detect_keywords(lower, _DEADLINE_PATTERNS)
    if deadline_match:
        base["deadline_claimed"] = True
        deadline_text = _extract_sentence(text, deadline_match.span())
        base["deadline_text"] = deadline_text
        base["deadline_days"] = _estimate_deadline_days(deadline_text)
        if any(token in lower for token in ["recoger", "entregar", "entrega"]):
            base["deadline_kind"] = "pickup"
        elif any(token in lower for token in ["pagar", "pago", "pagarlo"]):
            base["deadline_kind"] = "payment"
        else:
            base["deadline_kind"] = "decision"
        _append_evidence(
            evidence_items,
            _make_evidence("DEADLINE", deadline_text, base["deadline_days"], "regex", 0.7, turn_idx),
            window_turns,
        )

    other_buyer_match = _detect_keywords(lower, _OTHER_BUYER_PATTERNS)
    if other_buyer_match:
        base["other_buyer_claimed"] = True
        other_buyer_text = _extract_sentence(text, other_buyer_match.span())
        base["other_buyer_text"] = other_buyer_text
        base["other_buyer_offer_price"] = _extract_price(base["other_buyer_text"].lower())
        base["other_buyer_timing_text"] = _extract_timing_phrase(base["other_buyer_text"])
        confidence = 0.6 if "oferta" in lower or "comprador" in lower else 0.4
        _append_evidence(
            evidence_items,
            _make_evidence(
                "OTHER_BUYER",
                other_buyer_text,
                {
                    "offer_price": base["other_buyer_offer_price"],
                    "timing": base["other_buyer_timing_text"],
                },
                "regex",
                confidence,
                turn_idx,
            ),
            window_turns,
        )

    batna_match = _detect_keywords(lower, _BATNA_PATTERNS)
    if batna_match:
        base["batna_claimed"] = True
        batna_text = _extract_sentence(text, batna_match.span())
        base["batna_text"] = batna_text
        _append_evidence(
            evidence_items,
            _make_evidence("BATNA", batna_text, None, "regex", 0.6, turn_idx),
            window_turns,
        )

    urgency_match = _detect_keywords(lower, _URGENCY_PATTERNS)
    if urgency_match:
        base["urgency_claimed"] = True
        urgency_text = _extract_sentence(text, urgency_match.span())
        base["urgency_text"] = urgency_text
        base["urgency_reason"] = urgency_text[:120]
        _append_evidence(
            evidence_items,
            _make_evidence("URGENCY", urgency_text, None, "regex", 0.6, turn_idx),
            window_turns,
        )

    min_price_match = _detect_keywords(lower, _MIN_PRICE_PATTERNS)
    if min_price_match:
        base["min_price_claimed"] = True
        min_price_text = _extract_sentence(text, min_price_match.span())
        base["min_price_text"] = min_price_text
        _append_evidence(
            evidence_items,
            _make_evidence("MIN_PRICE", min_price_text, None, "regex", 0.6, turn_idx),
            window_turns,
        )

    price_firm_match = _detect_keywords(lower, _PRICE_FIRM_PATTERNS)
    if price_firm_match:
        price_firm_text = _extract_sentence(text, price_firm_match.span())
        base["price_firm_text"] = price_firm_text
        confidence = 0.6 if "precio" in price_firm_text.lower() else 0.4
        _append_evidence(
            evidence_items,
            _make_evidence("FIRMNESS", price_firm_text, None, "regex", confidence, turn_idx),
            window_turns,
        )

    evidence_match = _detect_keywords(lower, _EVIDENCE_PATTERNS)
    if evidence_match:
        base["evidence_offered"] = True
        evidence_text = _extract_sentence(text, evidence_match.span())
        base["evidence_text"] = evidence_text
        _append_evidence(
            evidence_items,
            _make_evidence("EVIDENCE_DOC", evidence_text, None, "regex", 0.6, turn_idx),
            window_turns,
        )

    concession_match = _detect_keywords(lower, _CONCESSION_PATTERNS)
    if concession_match:
        base["concession_made"] = True
        concession_text = _extract_sentence(text, concession_match.span())
        base["concession_text"] = concession_text
        _append_evidence(
            evidence_items,
            _make_evidence("CONCESSION", concession_text, None, "regex", 0.6, turn_idx),
            window_turns,
        )

    docs_found: List[str] = []
    for key, label in _DOCS_MAP.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            docs_found.append(label)
    if docs_found:
        base["docs_claimed"] = True
        base["docs_types"] = _merge_list(base["docs_types"], docs_found)
        _append_evidence(
            evidence_items,
            _make_evidence("DOCS", text, docs_found, "regex", 0.6, turn_idx),
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
    if conflict_hits:
        _append_evidence(
            evidence_items,
            _make_evidence("TONE", text, base["tone_signal"], "regex", 0.5, turn_idx),
            window_turns,
        )

    base["evidence_items"] = evidence_items
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
    by_type: dict[str, list[EvidenceItem]] = {}
    for item in items:
        by_type.setdefault(item.get("type", ""), []).append(item)

    manual_items: list[EvidenceItem] = []
    if world.get("price_mentioned") and not by_type.get("PRICE"):
        manual_items.append(
            _make_evidence(
                "PRICE", "", world.get("price_value"), "manual", confidence_min, None
            )
        )
    if world.get("deadline_claimed") and not by_type.get("DEADLINE"):
        manual_items.append(
            _make_evidence(
                "DEADLINE",
                world.get("deadline_text", ""),
                world.get("deadline_days"),
                "manual",
                confidence_min,
                None,
            )
        )
    if world.get("urgency_claimed") and not by_type.get("URGENCY"):
        manual_items.append(
            _make_evidence(
                "URGENCY", world.get("urgency_text", ""), None, "manual", confidence_min, None
            )
        )
    if world.get("other_buyer_claimed") and not by_type.get("OTHER_BUYER"):
        manual_items.append(
            _make_evidence(
                "OTHER_BUYER",
                world.get("other_buyer_text", ""),
                None,
                "manual",
                confidence_min,
                None,
            )
        )
    if world.get("concession_made") and not by_type.get("CONCESSION"):
        manual_items.append(
            _make_evidence(
                "CONCESSION",
                world.get("concession_text", ""),
                None,
                "manual",
                confidence_min,
                None,
            )
        )
    if world.get("docs_claimed") and not by_type.get("DOCS"):
        manual_items.append(
            _make_evidence(
                "DOCS", "", world.get("docs_types", []), "manual", confidence_min, None
            )
        )
    if world.get("min_price_claimed") and not by_type.get("MIN_PRICE"):
        manual_items.append(
            _make_evidence(
                "MIN_PRICE",
                world.get("min_price_text", ""),
                None,
                "manual",
                confidence_min,
                None,
            )
        )
    if world.get("price_firm") and not by_type.get("FIRMNESS"):
        manual_items.append(
            _make_evidence(
                "FIRMNESS",
                world.get("price_firm_text", ""),
                None,
                "manual",
                confidence_min,
                None,
            )
        )
    if world.get("evidence_offered") and not by_type.get("EVIDENCE_DOC"):
        manual_items.append(
            _make_evidence(
                "EVIDENCE_DOC",
                world.get("evidence_text", ""),
                None,
                "manual",
                confidence_min,
                None,
            )
        )
    if world.get("batna_claimed") and not by_type.get("BATNA"):
        manual_items.append(
            _make_evidence(
                "BATNA", world.get("batna_text", ""), None, "manual", confidence_min, None
            )
        )
    if world.get("tone_signal") and not by_type.get("TONE"):
        manual_items.append(
            _make_evidence(
                "TONE", "", world.get("tone_signal"), "manual", confidence_min, None
            )
        )

    if manual_items:
        world["evidence_items"] = list(items) + manual_items
        items = world["evidence_items"]
        by_type = {}
        for item in items:
            by_type.setdefault(item.get("type", ""), []).append(item)

    if items:
        world["price_mentioned"] = False
        world["deadline_claimed"] = False
        world["urgency_claimed"] = False
        world["other_buyer_claimed"] = False
        world["concession_made"] = False
        world["docs_claimed"] = False
        world["min_price_claimed"] = False
        world["price_firm"] = False
        world["evidence_offered"] = False
        world["batna_claimed"] = False

    def _best(item_type: str) -> EvidenceItem | None:
        candidates = [
            item for item in by_type.get(item_type, []) if item.get("confidence", 0.0) >= confidence_min
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda it: float(it.get("confidence", 0.0)), reverse=True)
        return candidates[0]

    if (best := _best("PRICE")):
        world["price_mentioned"] = True
        if best.get("value") is not None:
            world["price_value"] = float(best["value"])
    if (best := _best("DEADLINE")):
        world["deadline_claimed"] = True
        world["deadline_text"] = str(best.get("text", world.get("deadline_text", "")))
        if best.get("value") is not None:
            world["deadline_days"] = int(best["value"])
        if not world.get("deadline_kind") or world.get("deadline_kind") == "unknown":
            world["deadline_kind"] = "decision"
    if (best := _best("URGENCY")):
        world["urgency_claimed"] = True
        world["urgency_text"] = str(best.get("text", world.get("urgency_text", "")))
        world["urgency_reason"] = str(best.get("text", world.get("urgency_reason", "")))[:120]
    if (best := _best("OTHER_BUYER")):
        world["other_buyer_claimed"] = True
        world["other_buyer_text"] = str(best.get("text", world.get("other_buyer_text", "")))
    if (best := _best("CONCESSION")):
        world["concession_made"] = True
        world["concession_text"] = str(best.get("text", world.get("concession_text", "")))
    if (best := _best("DOCS")):
        world["docs_claimed"] = True
        if best.get("value"):
            world["docs_types"] = _merge_list(world.get("docs_types", []), list(best["value"]))
    if (best := _best("MIN_PRICE")):
        world["min_price_claimed"] = True
        world["min_price_text"] = str(best.get("text", world.get("min_price_text", "")))
    if (best := _best("FIRMNESS")):
        world["price_firm"] = True
        world["price_firm_text"] = str(best.get("text", world.get("price_firm_text", "")))
    if (best := _best("EVIDENCE_DOC")):
        world["evidence_offered"] = True
        world["evidence_text"] = str(best.get("text", world.get("evidence_text", "")))
    if (best := _best("BATNA")):
        world["batna_claimed"] = True
        world["batna_text"] = str(best.get("text", world.get("batna_text", "")))
    if (best := _best("TONE")):
        world["tone_signal"] = str(best.get("value", world.get("tone_signal", "neutral")))
        world["tone_confidence"] = max(
            float(world.get("tone_confidence", 0.0)), float(best.get("confidence", 0.0))
        )
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
        if "message_is_vague" in decisions and "message_is_vague" not in patch:
            patch["message_is_vague"] = bool(decisions.get("message_is_vague"))
        output = {**output, "world_patch": patch}
        validate_extractor_output(output)
        world = dict(base)
        for key, value in patch.items():
            world[key] = value
        if llm_evidence:
            world["evidence_items"] = list(base.get("evidence_items", [])) + llm_evidence
            world["world_state_meta"]["last_update_source"] = "llm"
        meta = build_extractor_meta(output)
        world = _derive_flags_from_evidence(world, confidence_min)
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
