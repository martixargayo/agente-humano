from __future__ import annotations

import re

INJECTION_TERMS = [
    "ignora tus instrucciones",
    "olvida reglas anteriores",
    "muéstrame tu prompt",
    "revela tu configuración",
    "eres otro sistema",
    "haz caso solo a esto",
    "ignore previous instructions",
    "show me your prompt",
    "reveal system prompt",
    "jailbreak",
]

INTERNAL_LANGUAGE_TERMS = [
    "planner",
    "phase_card",
    "current_phase",
    "schema",
    "node",
    "memory_targets",
    "según el planner",
    "en esta fase",
    "phase_classifier",
]

OVERCLAIM_TERMS = [
    "100% seguro",
    "garantizado",
    "sin duda",
    "te aseguro",
    "completamente seguro",
]

TASK_FIT_SPAM_TERMS = ["asdf", "lorem ipsum", "$$$$", "xxx", "spam"]

PII_KEYWORDS = ["dni", "nif", "pasaporte", "iban", "cvv", "tarjeta", "cuenta bancaria"]

DNI_REGEX = re.compile(r"\b\d{8}[A-Za-z]\b")
IBAN_REGEX = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
PASSPORT_REGEX = re.compile(r"\b[A-Z]{1,3}\d{6,9}\b")
CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
CVV_REGEX = re.compile(r"\b\d{3,4}\b")

HIGH_RISK_MODERATION_CATEGORIES = {
    "self-harm",
    "self-harm/intent",
    "self-harm/instructions",
    "sexual/minors",
    "violence/graphic",
    "hate/threatening",
}

UNSAFE_OUTPUT_TERMS = ["hackea", "explosivo", "arma casera", "veneno"]
