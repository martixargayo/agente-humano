from __future__ import annotations

from typing import Literal

from fastapi import HTTPException

from sessions.state import SessionState

SessionSurface = Literal['optimizador', 'interfaz_usuario']
SESSION_SURFACE_WORLD_STATE_KEY = '_session_surface'


def read_session_surface(state: SessionState) -> SessionSurface | None:
    world_state = state.world_state if isinstance(state.world_state, dict) else {}
    value = world_state.get(SESSION_SURFACE_WORLD_STATE_KEY)
    if value in {'optimizador', 'interfaz_usuario'}:
        return value
    return None


def bind_session_surface(*, state: SessionState, surface: SessionSurface) -> SessionSurface:
    if not isinstance(state.world_state, dict):
        state.world_state = {}
    state.world_state[SESSION_SURFACE_WORLD_STATE_KEY] = surface
    return surface


def ensure_session_surface(*, state: SessionState, surface: SessionSurface) -> SessionSurface:
    current = read_session_surface(state)
    if current is None:
        return bind_session_surface(state=state, surface=surface)
    if current != surface:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'session_surface_conflict',
                'session_id': state.session_id,
                'existing_surface': current,
                'requested_surface': surface,
            },
        )
    return current


def is_surface_owned(*, state: SessionState, surface: SessionSurface) -> bool:
    return read_session_surface(state) == surface
