# backend/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Literal, Tuple, TypedDict


# ---- Tipos básicos ----

Role = Literal["user", "assistant"]


class Message(TypedDict):
    role: Role
    content: str


SessionKey = Tuple[str, str]


@dataclass
class SessionState:
    user_id: str
    session_id: str

    # Resumen acumulado de todo lo "antiguo"
    summary: str = ""

    # Historial corto: últimos N turnos (ventana recortada)
    history: List[Message] = field(default_factory=list)

    # Info auxiliar
    turn_count: int = 0
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# Almacén global en RAM (MVP, sin DB)
SESSIONS: Dict[SessionKey, SessionState] = {}

# Si algún día quieres leer estos valores desde env, puedes moverlos a agent.py.
# Aquí solo documentamos que son "parámetros de diseño".
DEFAULT_CONTEXT_LIMIT_TURNS: int = 12        # a partir de cuántos turnos totales empezamos a resumir
DEFAULT_KEEP_LAST_TURNS: int = 4            # cuántos turnos recientes guardamos "enteros"


def _make_key(user_id: str, session_id: str) -> SessionKey:
    return (user_id, session_id)


def get_session_state(user_id: str, session_id: str) -> SessionState:
    """
    Recupera el estado de sesión para (user_id, session_id).
    Si no existe, lo crea.
    """
    key = _make_key(user_id, session_id)
    if key not in SESSIONS:
        SESSIONS[key] = SessionState(user_id=user_id, session_id=session_id)
    return SESSIONS[key]


def save_session_state(state: SessionState) -> None:
    """
    Guarda/actualiza el estado en el diccionario global.
    """
    key = _make_key(state.user_id, state.session_id)
    state.last_updated = datetime.now(timezone.utc)
    SESSIONS[key] = state


def add_message(state: SessionState, role: Role, content: str) -> None:
    """
    Añade un mensaje al historial corto (history).
    No hace trimming ni resumen: eso lo controla agent.py.
    """
    msg: Message = {"role": role, "content": content.strip()}
    state.history.append(msg)
    state.turn_count += 1
    state.last_updated = datetime.now(timezone.utc)


def reset_session_state(user_id: str, session_id: str) -> None:
    """
    Elimina (reset) el estado de una sesión.
    """
    key = _make_key(user_id, session_id)
    SESSIONS.pop(key, None)
