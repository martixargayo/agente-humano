# backend/normalizer.py
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# Modelo específico del normalizador (segunda LLM)
NORMALIZER_MODEL = os.getenv(
    "NORMALIZER_MODEL_NAME",
    os.getenv("SUMMARY_MODEL_NAME", os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")),
)

NORMALIZER_TEMPERATURE = float(os.getenv("NORMALIZER_TEMPERATURE", "0.0"))

normalizer_llm = ChatOpenAI(
    model=NORMALIZER_MODEL,
    temperature=NORMALIZER_TEMPERATURE,
)

NORMALIZER_SYSTEM_PROMPT = """
Eres un normalizador de estilo.
Tu única tarea es reescribir la respuesta que recibes manteniendo exactamente
el mismo significado e intención, pero ajustando el estilo.

Reglas:
- Devuelve solo UNA versión reescrita del texto, sin explicaciones ni comentarios.
- Máximo 2 frases cortas. Si puedes compactar en 1 frase natural, mejor.
- Estilo oral, directo, natural, sin tono corporativo ni académico.
- Elimina frases de validación meta como "Entiendo tu pregunta", "Claro que sí",
  "Por supuesto", "Buena pregunta", etc.
- Elimina disculpas innecesarias y cualquier referencia a ser IA, modelo, asistente, etc.
- No hagas listas ni bullets, responde en prosa corrida.
- No añadas información nueva ni cambies el mensaje de fondo.
- Si el texto ya cumple estas reglas, devuélvelo casi igual.
"""

normalizer_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", NORMALIZER_SYSTEM_PROMPT),
        ("user", "{text}"),
    ]
)


def normalize_text(raw_reply: str) -> str:
    """
    Normaliza una respuesta del modelo principal:
    - reescribe estilo
    - mantiene significado
    - devuelve máx. 1–2 frases
    """
    raw_reply = (raw_reply or "").strip()
    if not raw_reply:
        return ""

    messages = normalizer_prompt.format_messages(text=raw_reply)
    result = normalizer_llm.invoke(messages)
    return (result.content or "").strip()
