from __future__ import annotations

# Keys universales del "dominio" (no son universal_state; son campos simples “semánticos” comunes)
ALLOWED_UNIVERSAL_DOMAIN_KEYS: list[str] = [
    # ejemplo: tono/vaguedad y cosas generales
    "message_is_vague",
    "tone_signal",
    "tone_confidence",
    # si hay otros que no sean estrictamente negociación y que quieras conservar, ponlos aquí
]

# Keys ESPECÍFICAS de negociación
ALLOWED_NEGOTIATION_DOMAIN_KEYS: list[str] = [
    "price_mentioned",
    "price_value",
    "price_firm",
    "price_firm_text",
    "deadline_claimed",
    "deadline_text",
    "deadline_days",
    "deadline_kind",
    "urgency_claimed",
    "urgency_text",
    "urgency_reason",
    "other_buyer_claimed",
    "other_buyer_text",
    "other_buyer_offer_price",
    "other_buyer_timing_text",
    "concession_made",
    "concession_text",
    "batna_claimed",
    "batna_text",
    "min_price_claimed",
    "min_price_text",
    "docs_claimed",
    "docs_types",
    "evidence_offered",
    "evidence_text",
]
