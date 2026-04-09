from __future__ import annotations

from sessions.state import SessionState

from ..contexts import read_bound_conversacion_simple_context_from_session, resolve_conversacion_simple_context
from negociacion.orchestration.turn_execution_context import TurnExecutionContext


def build_conversacion_simple_turn_context(
    *,
    state: SessionState,
    entrypoint: str,
    entry_surface: str = "conversacion_simple",
    context_source: str = "internal_explicit",
    requested_context_id: str | None = None,
) -> TurnExecutionContext:
    bound = read_bound_conversacion_simple_context_from_session(state)
    effective_context_id = bound.context_id if bound is not None else (requested_context_id or "").strip() or None
    resolved = resolve_conversacion_simple_context(effective_context_id) if effective_context_id else None
    return TurnExecutionContext(
        user_id=state.user_id,
        session_id=state.session_id,
        execution_mode="stateful",
        effective_context_id=effective_context_id,
        requested_context_id=(requested_context_id or "").strip() or None,
        session_bound_context_id=bound.context_id if bound is not None else None,
        context_source=context_source,
        entry_surface=entry_surface,
        entrypoint=entrypoint,
        context_version=resolved.context_version if resolved is not None else None,
        flow_id=resolved.flow_id if resolved is not None else None,
    )
