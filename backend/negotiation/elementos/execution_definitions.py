import re

from ..config import get_negotiation_model_config

NEGOTIATION_CONFIG = get_negotiation_model_config()

EMBEDDINGS_MODEL = NEGOTIATION_CONFIG.embeddings.model
RAG_DIR = NEGOTIATION_CONFIG.rag_dir

EXECUTOR_MODEL = NEGOTIATION_CONFIG.executor.model
EXECUTOR_TEMPERATURE = NEGOTIATION_CONFIG.executor.temperature

SUMMARY_MODEL = NEGOTIATION_CONFIG.summary.model
SUMMARY_TEMPERATURE = NEGOTIATION_CONFIG.summary.temperature

OUTCOME_GOOD = "good"
OUTCOME_BAD = "bad"
OUTCOME_NEUTRAL = "neutral"

INFO_DELTA_KEYS = {
    "docs_claimed",
    "docs_types",
    "deadline_claimed",
    "deadline_text",
    "other_buyer_claimed",
    "concession_made",
    "concession_text",
    "price_mentioned",
    "price_value",
}

NUMBER_PATTERN = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\b")
OWN_NUMBER_CONTEXT = re.compile(
    r"\b(mi|mío|mios|mi presupuesto|puedo pagar|pago|te doy|mi oferta)\b",
    re.IGNORECASE,
)
PRICE_CONTEXT = re.compile(
    r"(€|euros|precio|pagar|oferta|te doy|me quedo en|lo dejo en)", re.IGNORECASE
)
