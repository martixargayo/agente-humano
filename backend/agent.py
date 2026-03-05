# backend/agent.py
from __future__ import annotations

import logging
import os
from typing import List, Tuple

import openai

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

# --- Modelos ---

# Modelo principal (para responder al usuario)
MAIN_MODEL = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")

# Modelo de resumen (puede ser más pequeño/barato)
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini")

# Temperaturas con posibilidad de override por .env
MAIN_TEMPERATURE = float(os.getenv("MAIN_TEMPERATURE", "0.7"))
SUMMARY_TEMPERATURE = float(os.getenv("SUMMARY_TEMPERATURE", "0.2"))

logger = logging.getLogger(__name__)


def _build_openai_client(*, client_name: str):
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("%s_openai_api_key_missing fallback_enabled=true", client_name)
        return None

    try:
        return openai.OpenAI()
    except Exception as exc:
        logger.warning("%s_client_init_error=%s", client_name, exc)
        return None


# Cliente principal del agente (Daniel)
llm_client = _build_openai_client(client_name="agent_main")

# Cliente para resumir (memoria comprimida de sesión)
summary_client = _build_openai_client(client_name="agent_summary")

# Parámetros de memoria (inspirados en trimming + summarizing)
CONTEXT_LIMIT_TURNS: int = int(
    os.getenv("CONTEXT_LIMIT_TURNS", DEFAULT_CONTEXT_LIMIT_TURNS)
)
KEEP_LAST_TURNS: int = int(
    os.getenv("KEEP_LAST_TURNS", DEFAULT_KEEP_LAST_TURNS)
)


# ---- Utilidades internas ----


def _format_messages_as_text(messages: List[Message]) -> str:
    """
    Convierte la lista de mensajes en un bloque de texto etiquetado,
    útil tanto para el resumen como para el contexto del LLM.
    """
    lines: List[str] = []
    for msg in messages:
        role = msg.get("role", "assistant")
        content = (msg.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            label = "Usuario"
        elif role == "assistant":
            label = "Agente"
        else:
            label = str(role).upper()

        lines.append(f"{label}: {content}")
    return "\n".join(lines).strip() or "(sin mensajes previos relevantes)"


def _user_turn_indices(history: List[Message]) -> List[int]:
    """
    Devuelve los índices en history donde empieza cada turno de usuario.
    (Un turno empieza cuando hay un mensaje con role == 'user').
    """
    return [i for i, m in enumerate(history) if m.get("role") == "user"]


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

    user_input = SUMMARY_USER_PROMPT.format(
        existing_summary=existing_summary,
        new_block=new_block,
    )

    if summary_client is None:
        state.summary = (existing_summary + "\n" + new_block).strip()
        return

    try:
        result = summary_client.responses.create(
            model=SUMMARY_MODEL,
            temperature=SUMMARY_TEMPERATURE,
            input=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
        )
        state.summary = (getattr(result, "output_text", "") or "").strip() or (
            existing_summary + "\n" + new_block
        ).strip()
    except Exception as exc:
        logger.warning("agent_summary_invoke_error=%s", exc)
        state.summary = (existing_summary + "\n" + new_block).strip()


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


def _build_conversation_user_input(state: SessionState, user_message: str) -> str:
    """
    Construye el bloque de usuario combinando:
    - summary (memoria larga)
    - history recortado (short-term window)
    - mensaje actual del usuario
    """
    summary_text = state.summary or "Aún no hay resumen de la conversación."
    recent_history_text = _format_messages_as_text(state.history)
    return CONVERSATION_USER_TEMPLATE.format(
        summary_text=summary_text,
        recent_history_text=recent_history_text,
        user_message=user_message,
    )


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

    # 3) Construir input para el LLM
    user_input = _build_conversation_user_input(state, user_message)

    # 4) Llamar al modelo principal
    if llm_client is None:
        raw_reply = "Entendido. ¿Qué condición te gustaría concretar ahora?"
    else:
        try:
            result = llm_client.responses.create(
                model=MAIN_MODEL,
                temperature=MAIN_TEMPERATURE,
                input=[
                    {"role": "system", "content": BASE_PERSONALITY_PROMPT},
                    {
                        "role": "system",
                        "content": "Usa el resumen más el historial reciente para responder al usuario de forma coherente y consistente.",
                    },
                    {"role": "user", "content": user_input},
                ],
            )
            raw_reply = (getattr(result, "output_text", "") or "").strip()
            if not raw_reply:
                raw_reply = "Entendido. ¿Qué condición te gustaría concretar ahora?"
        except Exception as exc:
            logger.warning("agent_main_invoke_error=%s", exc)
            raw_reply = "Entendido. ¿Qué condición te gustaría concretar ahora?"

    # DEBUG: ver qué sale de Daniel antes del normalizador
    print("\n===== RAW_DANIEL_OUTPUT =====")
    print(raw_reply)
    print("===== END_RAW_DANIEL_OUTPUT =====\n", flush=True)

    # 4.1) Normalizar estilo (máx. 1–2 frases, sin meta, etc.) +  Pasamos también el mensaje del usuario al normalizador
    reply_text = normalize_text(raw_reply, user_message)

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
