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
<normalizer>
Tu tarea es reescribir la respuesta de Daniel manteniendo el mismo
significado e intención, usando la mínima cantidad de palabras
necesarias y un tono oral humano, directo y conciso.

Reglas:

1. No cambies el tema, intención ni dirección del mensaje.
2. Si el mensaje ya es breve, natural y sin relleno (saludo, respuesta corta),
   devuélvelo igual sin modificarlo.
3. Aplica compresión solo si el mensaje tiene relleno, validaciones,
   explicaciones o más de 2 frases.
4. Elimina validaciones, suavizaciones y muletillas solo si existen.
5. Elimina reflexiones, interpretaciones y comentarios innecesarios.
6. Mantén máximo 1–2 frases si el mensaje era largo.
7. No añadas preguntas nuevas.
8. Conserva una sola pregunta solo si el mensaje ya tenía una.
9. Mantén tono oral humano: directo, breve, sin adornos.
10. No añadas ni inventes información.

Devuelve solo el mensaje final normalizado.
</normalizer>

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
