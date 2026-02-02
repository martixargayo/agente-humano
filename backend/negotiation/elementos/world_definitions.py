import os
import re

# Thresholds y configuración
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

# Listas y Regex (sin guiones bajos)
PRICE_KEYWORDS = [
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

DEADLINE_PATTERNS = [
    r"\bhoy\b",
    r"\bmañana\b",
    r"\besta semana\b",
    r"\beste finde\b",
    r"\bantes de\b",
    r"\bpara el\b",
    r"\ben \d+ días\b",
    r"\ben \d+ semanas\b",
]

TIMING_PATTERNS = [
    r"\bhoy\b",
    r"\bmañana\b",
    r"\besta semana\b",
    r"\beste finde\b",
    r"\bantes de\b",
    r"\bpara el\b",
    r"\ben \d+ días\b",
    r"\ben \d+ semanas\b",
]

OTHER_BUYER_PATTERNS = [
    r"otro comprador",
    r"otra persona",
    r"otro interesado",
    r"hay interesados",
    r"me han ofrecido",
    r"ya tengo oferta",
]

BATNA_PATTERNS = [
    r"tengo otro interesado",
    r"otro interesado",
    r"otro comprador",
    r"me lo quedo",
    r"me lo quedar[ée]",
    r"lo llevo a compraventa",
    r"me lo compra mi primo",
]

URGENCY_PATTERNS_STRONG = [
    r"me urge",
    r"tengo prisa",
    r"necesito vender ya",
    r"necesito el dinero",
    r"me viene la reforma",
]

MIN_PRICE_PATTERNS = [
    r"de\s+\d+.*no bajo",
    r"mi mínimo es",
    r"mi minimo es",
    r"no bajo de",
]

PRICE_FIRM_PATTERNS = [
    r"precio fijo",
    r"no negociable",
    r"no negocio",
    r"precio cerrado",
]

EVIDENCE_PATTERNS = [
    r"tengo factura",
    r"tengo informe",
    r"te enseño papeles",
    r"tengo papeles",
    r"te puedo mostrar",
]

CONCESSION_PATTERNS = [
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

DOCS_MAP = {
    "itv": "ITV",
    "factura": "facturas",
    "facturas": "facturas",
    "libro": "libro",
    "mantenimiento": "libro",
    "informe": "informe",
    "dgt": "DGT",
    "historial": "historial",
}

FRIENDLY_MARKERS = ["gracias", "sin problema", "encantado", "perfecto"]
TENSE_MARKERS = ["no tengo tiempo", "último", "ultima", "ya", "prisa", "urge"]
CONFLICT_MARKERS = ["no pienso", "ni de broma", "no voy a", "olvídalo"]
ACCEPT_PATTERNS = [
    r"\bvale\b",
    r"\bde acuerdo\b",
    r"\bok(?:ay)?\b",
    r"\bperfecto\b",
    r"\bme parece bien\b",
    r"\bme sirve\b",
]
NEGATION_WINDOW = r"(?:\bno\b|\bpero\s+no\b|\bpara\s+nada\b|\bni\s+de\s+broma\b)"
NEGATION_AFTER = re.compile(
    r"^\s*(?:,?\s*)?(?:no\b|pero\s+no\b|para\s+nada\b|ni\s+de\s+broma\b)",
    flags=re.IGNORECASE,
)
EVASION_MARKERS = [
    "no sé",
    "no se",
    "como quieras",
    "da igual",
    "lo que tú digas",
    "no estoy seguro",
    "depende",
]
SOFT_COMMITMENT_MARKERS = [
    "podría",
    "quizá",
    "quizas",
    "me lo pensaría",
    "me lo pensare",
    "podemos verlo",
    "si me lo dejas",
]

# Patrones de gate utils
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_PATTERN = re.compile(r"\b\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}\b")
URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
SYMBOL_PATTERN = re.compile(r"[%€$@#\+\-]")
ATTACHMENT_HINTS = (
    "foto",
    "fotos",
    "pdf",
    "documento",
    "documentos",
    "adjunto",
    "adjunta",
    "archivo",
    "archivos",
    "imagen",
    "imágenes",
)
