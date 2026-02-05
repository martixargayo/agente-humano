from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Literal, Optional, Tuple

from ..elementos.world_definitions import (
    ATTACHMENT_HINTS,
    EMAIL_PATTERN,
    PHONE_PATTERN,
    SYMBOL_PATTERN,
    URL_PATTERN,
)

VoiceModality = Literal["text", "voice"]
ConversationMode = Literal["general", "negotiation"]

# =============== VOICE LEXICONS (UNIVERSAL) ===============
# Nota: normalizamos a minúsculas y quitamos puntuación básica
VOICE_QUESTION_WORDS = {
    "que",
    "qué",
    "como",
    "cómo",
    "cuando",
    "cuándo",
    "donde",
    "dónde",
    "por que",
    "por qué",
    "porque",
    "cuanto",
    "cuánto",
    "cual",
    "cuál",
    "quien",
    "quién",
}
VOICE_QUESTION_SOFT_PATTERNS = [
    re.compile(
        r"\b(me\s+puedes|me\s+podrias|me\s+podrías|podrias|podrías|puedes|me\s+dices|me\s+dirias|me\s+dirías)\b",
        re.I,
    ),
    re.compile(r"\b(quieres\s+decirme|me\s+puedes\s+decir)\b", re.I),
]

VOICE_SHORT_ACK_TOKENS = {
    "vale",
    "ok",
    "okay",
    "perfecto",
    "hecho",
    "trato",
    "venga",
    "ya",
    "ajá",
    "aja",
    "mmm",
    "mhmm",
    "si",
    "sí",
    "claro",
    "bien",
    "genial",
}

VOICE_NEGATION_TOKENS = {
    "no",
    "nunca",
    "jamás",
    "jamas",
    "ni",
    "para nada",
    "en absoluto",
}

VOICE_REFUSAL_PHRASES = [
    "no quiero",
    "no me interesa",
    "olvidalo",
    "olvídalo",
    "ni de broma",
    "paso",
    "dejalo",
    "déjalo",
    "déjalo ya",
]

VOICE_FILLERS = {"eh", "mmm", "bueno", "pues", "a ver"}

# =============== VOICE LEXICONS (NEGOTIATION-ONLY) ===============
NEG_AMOUNT_TOKENS = {"euro", "euros", "pavos", "mil", "miles", "k", "barato", "caro", "eur"}
NEG_TIME_PHRASES = [
    "hoy",
    "mañana",
    "manana",
    "esta semana",
    "este finde",
    "antes de",
    "para el",
    "en ",
    "dias",
    "días",
    "semanas",
]
NEG_PRESSURE_PHRASES = ["me urge", "prisa", "ya", "hoy mismo", "necesito", "cuanto antes"]
NEG_COMPETITION_PHRASES = [
    "otro interesado",
    "otra persona",
    "me han ofrecido",
    "tengo oferta",
    "ya tengo oferta",
    "otro comprador",
]
NEG_FIRMNESS_PHRASES = ["no negociable", "precio fijo", "no negocio", "cerrado", "no bajo"]
NEG_CONCESSION_PHRASES = [
    "te lo dejo",
    "lo dejo en",
    "ultima oferta",
    "última oferta",
    "puedo bajar",
    "rebajo",
    "descuento",
    "me ajusto",
]

# =============== FEATURE KEYS USED BY MATERIAL CHANGE ===============
VOICE_UNIVERSAL_MATERIAL_KEYS = [
    "len_bucket",
    "token_count_bucket",
    "has_question_words",
    "question_strength",
    "is_short_ack",
    "has_negation",
    "has_refusal_phrase",
    "repeat_ratio_bucket",
    # opcional: "is_filler_heavy",
]
VOICE_NEGOTIATION_MATERIAL_KEYS = [
    "has_amount_mention",
    "has_time_terms",
    "has_pressure_terms",
    "has_competition_terms",
    "has_firmness_terms",
    "has_concession_terms",
]

_PUNCT_RE = re.compile(r"[^\w\sáéíóúüñ€$]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def _norm_voice(text: str) -> str:
    t = (text or "").strip().lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def _tokens_voice(text: str) -> list[str]:
    t = _norm_voice(text)
    return [tok for tok in t.split(" ") if tok]


def _contains_any_substring(norm_text: str, phrases: Iterable[str]) -> bool:
    for ph in phrases:
        if ph in norm_text:
            return True
    return False


def _len_bucket(raw: str) -> str:
    n = len(raw or "")
    if n == 0:
        return "0"
    if n <= 4:
        return "1_4"
    if n <= 12:
        return "5_12"
    if n <= 40:
        return "13_40"
    return "41_plus"


def _token_bucket_voice(tokens: list[str]) -> str:
    c = len(tokens)
    if c == 0:
        return "0"
    if c <= 2:
        return "1_2"
    if c <= 6:
        return "3_6"
    if c <= 14:
        return "7_14"
    return "15_plus"


def _has_question_words(tokens: list[str], norm_text: str) -> bool:
    tok_set = set(tokens)
    if tok_set.intersection({w for w in VOICE_QUESTION_WORDS if " " not in w}):
        return True
    if "por" in tok_set and ("que" in tok_set or "qué" in tok_set):
        return True
    if any(p.search(norm_text) for p in VOICE_QUESTION_SOFT_PATTERNS):
        return True
    return False


def _question_strength(tokens: list[str], norm_text: str) -> str:
    if not tokens:
        return "none"
    if any(p.search(norm_text) for p in VOICE_QUESTION_SOFT_PATTERNS):
        return "soft"
    if tokens[0] in {
        "que",
        "qué",
        "como",
        "cómo",
        "cuando",
        "cuándo",
        "donde",
        "dónde",
        "cuanto",
        "cuánto",
        "cual",
        "cuál",
        "quien",
        "quién",
    }:
        return "direct"
    if set(tokens).intersection(
        {
            "que",
            "qué",
            "como",
            "cómo",
            "cuando",
            "cuándo",
            "donde",
            "dónde",
            "cuanto",
            "cuánto",
            "cual",
            "cuál",
            "quien",
            "quién",
        }
    ):
        return "direct"
    return "none"


def _is_short_ack(tokens: list[str]) -> bool:
    if not tokens:
        return False
    if len(tokens) > 3:
        return False
    return all(tok in VOICE_SHORT_ACK_TOKENS for tok in tokens)


def _has_negation(tokens: list[str], norm_text: str) -> bool:
    if (
        "no" in tokens
        or "ni" in tokens
        or "nunca" in tokens
        or "jamás" in tokens
        or "jamas" in tokens
    ):
        return True
    return _contains_any_substring(norm_text, {"para nada", "en absoluto"})


def _has_refusal_phrase(norm_text: str) -> bool:
    return _contains_any_substring(norm_text, VOICE_REFUSAL_PHRASES)


def _token_overlap_ratio(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa.intersection(sb))
    denom = max(len(sa), len(sb))
    if denom == 0:
        return 0.0
    return inter / float(denom)


def _repeat_ratio_bucket(prev_text: Optional[str], curr_text: str) -> str:
    if not prev_text:
        return "none"
    a = _tokens_voice(prev_text)
    b = _tokens_voice(curr_text)
    r = _token_overlap_ratio(a, b)
    if r < 0.30:
        return "none"
    if r <= 0.60:
        return "low"
    return "high"


def _is_filler_heavy(tokens: list[str]) -> bool:
    if not tokens:
        return False
    filler = sum(1 for t in tokens if t in VOICE_FILLERS)
    return (filler / float(len(tokens))) > 0.25


def _neg_has_amount(norm_text: str, tokens: list[str]) -> bool:
    if re.search(r"\d+", norm_text):
        return True
    return bool(set(tokens).intersection(NEG_AMOUNT_TOKENS))


def _neg_flag(norm_text: str, phrases: list[str]) -> bool:
    return _contains_any_substring(norm_text, phrases)


def _voice_negotiation_flags(norm_text: str, tokens: list[str]) -> dict[str, bool]:
    return {
        "has_amount_mention": _neg_has_amount(norm_text, tokens),
        "has_time_terms": _neg_flag(norm_text, NEG_TIME_PHRASES),
        "has_pressure_terms": _neg_flag(norm_text, NEG_PRESSURE_PHRASES),
        "has_competition_terms": _neg_flag(norm_text, NEG_COMPETITION_PHRASES),
        "has_firmness_terms": _neg_flag(norm_text, NEG_FIRMNESS_PHRASES),
        "has_concession_terms": _neg_flag(norm_text, NEG_CONCESSION_PHRASES),
    }


def _length_bucket(length: int) -> str:
    if length <= 0:
        return "0"
    if length <= 4:
        return "1_4"
    if length <= 12:
        return "5_12"
    if length <= 40:
        return "13_40"
    return "41_plus"


def _token_bucket(count: int) -> str:
    if count <= 0:
        return "0"
    if count <= 2:
        return "1_2"
    if count <= 6:
        return "3_6"
    if count <= 14:
        return "7_14"
    return "15_plus"


def _input_shape_features_text_existing(text: str) -> Dict[str, Any]:
    raw = text or ""
    length = len(raw)
    digits_count = sum(1 for ch in raw if ch.isdigit())
    token_count = len(re.findall(r"\w+", raw, flags=re.UNICODE))
    lowered = raw.lower()
    return {
        "len_bucket": _length_bucket(length),
        "token_count_bucket": _token_bucket(token_count),
        "has_digits": digits_count > 0,
        "digits_count_bucket": "0" if digits_count == 0 else ("1_2" if digits_count <= 2 else "3_plus"),
        "has_currency": any(sym in raw for sym in ("€", "$")),
        "has_question": "?" in raw,
        "has_exclamation": "!" in raw,
        "has_url": bool(URL_PATTERN.search(raw)),
        "has_attachment": any(hint in lowered for hint in ATTACHMENT_HINTS),
        "has_email": bool(EMAIL_PATTERN.search(raw)),
        "has_phone": bool(PHONE_PATTERN.search(raw)),
        "has_symbol": bool(SYMBOL_PATTERN.search(raw)),
    }


def _input_shape_changed_materially_text_existing(
    prev_features: Dict[str, Any] | None,
    current_features: Dict[str, Any],
) -> Tuple[bool, list[str]]:
    if not prev_features:
        return True, ["no_prev_features"]
    material_keys = [
        "len_bucket",
        "token_count_bucket",
        "has_digits",
        "digits_count_bucket",
        "has_currency",
        "has_question",
        "has_exclamation",
        "has_url",
        "has_attachment",
    ]
    changed_keys = [
        key for key in material_keys if prev_features.get(key) != current_features.get(key)
    ]
    return bool(changed_keys), changed_keys


def input_shape_features(
    text: str,
    modality: VoiceModality = "text",
    prev_text: Optional[str] = None,
    conversation_mode: ConversationMode = "general",
) -> Dict[str, Any]:
    if modality != "voice":
        return _input_shape_features_text_existing(text)

    raw = text or ""
    norm = _norm_voice(raw)
    toks = _tokens_voice(raw)

    feats: Dict[str, Any] = {
        "len_bucket": _len_bucket(raw),
        "token_count_bucket": _token_bucket_voice(toks),
        "has_question_words": _has_question_words(toks, norm),
        "question_strength": _question_strength(toks, norm),
        "is_short_ack": _is_short_ack(toks),
        "has_negation": _has_negation(toks, norm),
        "has_refusal_phrase": _has_refusal_phrase(norm),
        "repeat_ratio_bucket": _repeat_ratio_bucket(prev_text, raw),
    }

    if conversation_mode == "negotiation":
        feats.update(_voice_negotiation_flags(norm, toks))

    return feats


def input_shape_changed_materially(
    prev_features: Dict[str, Any] | None,
    curr_features: Dict[str, Any],
    modality: VoiceModality = "text",
    conversation_mode: ConversationMode = "general",
) -> Tuple[bool, list[str]]:
    prev_features = prev_features or {}
    changed: list[str] = []

    if modality != "voice":
        return _input_shape_changed_materially_text_existing(prev_features, curr_features)

    keys = list(VOICE_UNIVERSAL_MATERIAL_KEYS)
    if conversation_mode == "negotiation":
        keys += VOICE_NEGOTIATION_MATERIAL_KEYS

    for k in keys:
        if prev_features.get(k) != curr_features.get(k):
            changed.append(k)

    return (len(changed) > 0), changed
