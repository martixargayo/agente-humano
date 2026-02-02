import os
import re

NEGOTIATION_DIR = os.path.dirname(os.path.dirname(__file__))

EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL_NAME", "text-embedding-3-small")
DEFAULT_RAG_DIR = os.path.join(NEGOTIATION_DIR, "policy_docs")
RAG_DIR = os.getenv("NEGOTIATION_RAG_DIR", DEFAULT_RAG_DIR)

EXECUTOR_MODEL = os.getenv(
    "EXECUTOR_MODEL_NAME",
    os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
)
EXECUTOR_TEMPERATURE = float(os.getenv("EXECUTOR_TEMPERATURE", "0.7"))

SUMMARY_MODEL = os.getenv(
    "SUMMARY_MODEL_NAME",
    os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
)
SUMMARY_TEMPERATURE = float(os.getenv("SUMMARY_TEMPERATURE", "0.2"))

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
