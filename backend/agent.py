# backend/agent.py
from __future__ import annotations

import os
from typing import List, Tuple

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

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

MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

# Modelo principal del agente
llm = ChatOpenAI(
    model=MODEL_NAME,
    temperature=0.7,
)

# Modelo para resumir (puede ser el mismo, pero con menos temperatura)
summary_llm = ChatOpenAI(
    model=MODEL_NAME,
    temperature=0.2,
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
    - Llama al modelo.
    - Añade la respuesta del agente a state.history.
    - Guarda el estado.
    """

    # 1) Añadir el mensaje del usuario al historial
    add_message(state, role="user", content=user_message)

    # 2) Trimming + summarizing si toca (según nº de turnos)
    _maybe_trim_and_summarize(state)

    # 3) Construir mensajes para el LLM
    messages = _build_conversation_messages(state, user_message)

    # 4) Llamar al modelo
    result = llm.invoke(messages)
    reply_text = result.content.strip()

    # 5) Añadir respuesta del agente al historial
    add_message(state, role="assistant", content=reply_text)

    # (Opcional) Podríamos volver a llamar a _maybe_trim_and_summarize() aquí,
    # pero como el criterio depende de turnos de usuario, no es necesario.

    # 6) Guardar estado
    save_session_state(state)

    return reply_text, state
