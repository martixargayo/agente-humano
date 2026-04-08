from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sessions.state import SessionState, get_session_state, get_session_store
from sessions.surface_scope import is_surface_owned

PREFERRED_TRACE_KEYS = ["negotiation_canonical_traces", "conversation_simple_canonical_traces"]


def iter_session_entries() -> Iterable[tuple[str, str, SessionState]]:
    yield from get_session_store().iter_entries()


def get_state(user_id: str, session_id: str) -> SessionState | None:
    return get_session_store().get(user_id=user_id, session_id=session_id)



def iter_optimizer_session_entries() -> Iterable[tuple[str, str, SessionState]]:
    for user_id, session_id, state in iter_session_entries():
        if is_surface_owned(state=state, surface='optimizador'):
            yield user_id, session_id, state


def get_optimizer_state(user_id: str, session_id: str) -> SessionState | None:
    state = get_state(user_id, session_id)
    if state is None or not is_surface_owned(state=state, surface='optimizador'):
        return None
    return state

def session_key(user_id: str, session_id: str) -> str:
    return f"{user_id}::{session_id}"


def parse_session_key(value: str) -> tuple[str, str]:
    if "::" not in value:
        raise ValueError("session_key inválida")
    user_id, session_id = value.split("::", 1)
    if not user_id or not session_id:
        raise ValueError("session_key inválida")
    return user_id, session_id


def resolve_traces(state: SessionState, memory_key: str | None = None) -> list[dict[str, Any]]:
    if memory_key:
        candidate = state.world_state.get(f"{memory_key}_traces")
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]

    for key in PREFERRED_TRACE_KEYS:
        candidate = state.world_state.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]

    fallback_keys = sorted(
        key for key, value in state.world_state.items() if key.endswith("_traces") and isinstance(value, list)
    )
    for key in fallback_keys:
        value = state.world_state.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []
