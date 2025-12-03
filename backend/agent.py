# backend/agent.py
from __future__ import annotations

import os
from typing import List, Tuple

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from normalizer import normalize_text

from state import (
    SessionState,
    Message,
    add_message,
    save_session_state,
    DEFAULT_CONTEXT_LIMIT_TURNS,
    DEFAULT_KEEP_LAST_TURNS,
)
from prompts import (
    BASE_PERSONALITY_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_USER_PROMPT,
    CONVERSATION_USER_TEMPLATE,
)

# Cargar variables de entorno (.env)
load_dotenv()

# --- Modelos ---

# Modelo principal (para responder al usuario)
MAIN_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

# Modelo de resumen (puede ser más pequeño/barato)
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini")

# Temperaturas con posibilidad de override por .env
MAIN_TEMPERATURE = float(os.getenv("MAIN_TEMPERATURE", "0.7"))
SUMMARY_TEMPERATURE = float(os.getenv("SUMMARY_TEMPERATURE", "0.2"))

# Modelo principal del agente (Daniel)
llm = ChatOpenAI(
    model=MAIN_MODEL,
    temperature=MAIN_TEMPERATURE,
)

# Modelo para resumir (memoria comprimida de sesión)
summary_llm = ChatOpenAI(
    model=SUMMARY_MODEL,
    temperature=SUMMARY_TEMPERATURE,
)

# Parámetros de memoria (inspirados en trimming + summarizing)
CONTEXT_LIMIT_TURNS: int = int(
    os.getenv("CONTEXT_LIMIT_TURNS", DEFAULT_CONTEXT_LIMIT_TURNS)
)
KEEP_LAST_TURNS: int = int(
    os.getenv("KEEP_LAST_TURNS", DEFAULT_KEEP_LAST_TURNS)
)

# --- Prompts LangChain ---

summary_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SUMMARY_SYSTEM_PROMPT),
        ("user", SUMMARY_USER_PROMPT),
    ]
)

conversation_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", BASE_PERSONALITY_PROMPT),
        (
            "system",
            "Usa el resumen más el historial reciente para responder al usuario "
            "de forma coherente y consistente.",
        ),
        ("user", CONVERSATION_USER_TEMPLATE),
    ]
)


# ---- Utilidades internas ----

def _format_messages_as_text(messages: List[Message]) -> str:
    """
    Convierte la lista de mensajes en un bloque de texto etiquetado,
    útil tanto para el resumen como para el contexto del LLM.
    """
    lines: List[str] = []
    for msg in messages:
        role = msg["role"]
        label = "Usuario" if role == "user" else "Agente"
        lines.append(f"{label}: {msg['content']}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


def _user_turn_indices(history: List[Message]) -> List[int]:
    """
    Devuelve los índices en history donde empieza cada turno de usuario.
    (Un turno empieza cuando hay un mensaje con role == 'user').
    """
    return [i for i, m in enumerate(history) if m["role"] == "user"]


def _should_summarize(history: List[Message]) -> bool:
    """
    Decide si hay que resumir en función del nº de turnos de usuario.
    (Ahora mismo no se usa directamente, pero lo dejamos por claridad).
    """
    return len(_user_turn_indices(history)) > CONTEXT_LIMIT_TURNS


def _summarize_prefix_into_state(
    state: SessionState,
    prefix_messages: List[Message],
) -> None:
    """
    Resume el bloque 'prefix_messages' y lo integra en state.summary.
    Después NO toca state.history: eso se hace fuera (trimming).
    """
    if not prefix_messages:
        return

    existing_summary = state.summary or ""
    new_block = _format_messages_as_text(prefix_messages)

    messages = summary_prompt.format_messages(
        existing_summary=existing_summary,
        new_block=new_block,
    )

    result = summary_llm.invoke(messages)
    state.summary = result.content.strip()


def _maybe_trim_and_summarize(state: SessionState) -> None:
    """
    Implementa la lógica de trimming + summarizing:

    - Si nº de turnos de usuario > CONTEXT_LIMIT_TURNS:
        - Calcula índices de turnos de usuario.
        - Determina el límite para conservar los últimos KEEP_LAST_TURNS turnos.
        - Resume todo lo anterior en state.summary.
        - Deja en state.history solo los últimos KEEP_LAST_TURNS turnos.
    """
    history = state.history
    user_indices = _user_turn_indices(history)

    if len(user_indices) <= CONTEXT_LIMIT_TURNS:
        return  # todavía no hace falta resumir

    # Nos aseguramos de que KEEP_LAST_TURNS sea al menos 1 y no exceda el nº de turnos reales
    keep_last = max(1, min(KEEP_LAST_TURNS, len(user_indices)))

    # Índice (en history) del PRIMER turno que queremos conservar sin resumir
    first_kept_user_idx = user_indices[-keep_last]

    prefix = history[:first_kept_user_idx]
    suffix = history[first_kept_user_idx:]

    # 1) Resumir prefix + integrarlo en summary
    _summarize_prefix_into_state(state, prefix)

    # 2) Mantener sólo suffix en el historial corto
    state.history = suffix


def _build_conversation_messages(
    state: SessionState,
    user_message: str,
):
    """
    Construye los mensajes (para LangChain) combinando:
    - summary (memoria larga)
    - history recortado (short-term window)
    - mensaje actual del usuario
    """
    summary_text = state.summary or "Aún no hay resumen de la conversación."
    recent_history_text = _format_messages_as_text(state.history)

    messages = conversation_prompt.format_messages(
        summary=summary_text,
        recent_history=recent_history_text,
        user_message=user_message,
    )
    return messages


# ---- Punto de entrada principal del agente ----

def run_agent(
    state: SessionState,
    user_message: str,
) -> Tuple[str, SessionState]:
    """
    - Añade el mensaje del usuario a state.history.
    - Si se supera el límite de turnos, resume + recorta.
    - Construye el prompt de conversación.
    - Llama al modelo principal (Daniel).
    - Añade la respuesta del agente a state.history.
    - Guarda el estado.
    """

    # 1) Añadir el mensaje del usuario al historial
    add_message(state, role="user", content=user_message)

    # 2) Trimming + summarizing si toca (según nº de turnos)
    _maybe_trim_and_summarize(state)

    # 3) Construir mensajes para el LLM
    messages = _build_conversation_messages(state, user_message)

    # 4) Llamar al modelo principal
    result = llm.invoke(messages)
    raw_reply = result.content.strip()

    # DEBUG: ver qué sale de Daniel antes del normalizador
    print("\n===== RAW_DANIEL_OUTPUT =====")
    print(raw_reply)
    print("===== END_RAW_DANIEL_OUTPUT =====\n", flush=True)

    # 4.1) Normalizar estilo (máx. 1–2 frases, sin meta, etc.)
    reply_text = normalize_text(raw_reply)

    # DEBUG: ver qué queda después de normalizar
    print("\n===== NORMALIZED_OUTPUT =====")
    print(reply_text)
    print("===== END_NORMALIZED_OUTPUT =====\n", flush=True)

    # 5) Añadir respuesta del agente al historial (solo la versión normalizada)
    add_message(state, role="assistant", content=reply_text)

    # 6) Guardar estado
    save_session_state(state)

    # 7) Devolver al usuario la versión ya normalizada
    return reply_text, state

