from __future__ import annotations

import re
import unicodedata
from typing import List

from ..elementos.world_definitions import (
    CONFLICT_MARKERS,
    EVASION_MARKERS,
    FRIENDLY_MARKERS,
    SOFT_COMMITMENT_MARKERS,
    TENSE_MARKERS,
)
from ..schemas import WorldState, default_world_state


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _normalize_short(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^\w\s€]", "", normalized.lower())
    return re.sub(r"\s+", " ", cleaned).strip()[:80]


def _previous_user_message(recent_history: list[dict]) -> str:
    for item in reversed(recent_history):
        if item.get("role") == "user":
            return str(item.get("content", "") or "")
    return ""


def _tone_hits_from_message(text: str) -> list[str]:
    lower = text.lower()
    hits: list[str] = []
    for marker in FRIENDLY_MARKERS:
        if marker in lower:
            hits.append(f"friendly:{marker}")
    for marker in TENSE_MARKERS:
        if marker in lower:
            hits.append(f"tense:{marker}")
    for marker in CONFLICT_MARKERS:
        if marker in lower:
            hits.append(f"tense:{marker}")
    return hits


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


def _match_affirmation(text_lower: str) -> bool:
    from ..elementos.world_definitions import ACCEPT_PATTERNS, NEGATION_AFTER, NEGATION_WINDOW

    for pat in ACCEPT_PATTERNS:
        match = re.search(pat, text_lower)
        if not match:
            continue
        before = text_lower[max(0, match.start() - 20) : match.start()]
        after = text_lower[match.end() : match.end() + 25]
        if re.search(NEGATION_WINDOW + r"\s*$", before):
            continue
        if NEGATION_AFTER.search(after):
            continue
        return True
    return False


def extract_interaction_signals(
    user_message: str,
    prev_world: WorldState | None,
    recent_history: list[dict] | str | None = None,
    tone_signal: str | None = None,
    prev_interaction: dict | None = None,
) -> dict:
    text = _normalize_text(user_message)
    lower = text.lower()
    recent_history = _coerce_recent_history(recent_history)
    prev_world = prev_world or default_world_state()
    prev_interaction = prev_interaction or {}
    prev_domain = (prev_world.get("universal_domain") or {}) if isinstance(prev_world, dict) else {}
    prev_tone = prev_domain.get("tone_signal", "neutral")
    if tone_signal is None:
        tone_hits = _tone_hits_from_message(text)
        tone_signal = _derive_tone_signal(tone_hits)

    implicit_acceptance = _match_affirmation(lower)
    evasion_detected = any(marker in lower for marker in EVASION_MARKERS)
    soft_commitment = any(marker in lower for marker in SOFT_COMMITMENT_MARKERS)
    prev_user = _normalize_short(_previous_user_message(recent_history))
    loop_hint = bool(prev_user and prev_user == _normalize_short(text))

    escalation_signal = "none"
    if prev_tone != tone_signal:
        if tone_signal == "tense":
            escalation_signal = "up"
        elif prev_tone == "tense" and tone_signal in {"neutral", "friendly"}:
            escalation_signal = "down"
    if prev_interaction.get("loop_hint") and not loop_hint:
        loop_hint = False

    return {
        "implicit_acceptance": implicit_acceptance,
        "escalation_signal": escalation_signal,
        "loop_hint": loop_hint,
        "evasion_detected": evasion_detected,
        "soft_commitment": soft_commitment,
    }
