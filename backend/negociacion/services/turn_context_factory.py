from __future__ import annotations

from sessions.state import SessionState

from ..contexts import read_bound_context_from_session, resolve_negotiation_context
from ..orchestration.turn_execution_context import TurnExecutionContext


def _build_stateful_context(
    *,
    state: SessionState,
    requested_context_id: str | None,
    entry_surface: str,
    entrypoint: str,
    context_source: str,
) -> TurnExecutionContext:
    bound = read_bound_context_from_session(state)
    effective_context_id = bound.context_id if bound is not None else (requested_context_id or "").strip() or None
    resolved = resolve_negotiation_context(effective_context_id) if effective_context_id else None
    return TurnExecutionContext(
        user_id=state.user_id,
        session_id=state.session_id,
        execution_mode="stateful",
        effective_context_id=effective_context_id,
        requested_context_id=(requested_context_id or "").strip() or None,
        session_bound_context_id=bound.context_id if bound is not None else None,
        context_source=context_source,  # type: ignore[arg-type]
        entry_surface=entry_surface,
        entrypoint=entrypoint,
        context_version=resolved.context_version if resolved is not None else None,
        flow_id=resolved.flow_id if resolved is not None else None,
    )


def build_interfaz_usuario_turn_context(*, state: SessionState, entrypoint: str, requested_context_id: str | None = None) -> TurnExecutionContext:
    return _build_stateful_context(
        state=state,
        requested_context_id=requested_context_id,
        entry_surface="interfaz_usuario",
        entrypoint=entrypoint,
        context_source="interfaz_usuario_session_bound",
    )


def build_optimizador_turn_context(*, state: SessionState, entrypoint: str, requested_context_id: str | None = None) -> TurnExecutionContext:
    return _build_stateful_context(
        state=state,
        requested_context_id=requested_context_id,
        entry_surface="optimizador",
        entrypoint=entrypoint,
        context_source="optimizador_session_bound",
    )


def build_api_negociar_turn_context(*, state: SessionState, requested_context_id: str, entrypoint: str = "/negociar") -> TurnExecutionContext:
    return _build_stateful_context(
        state=state,
        requested_context_id=requested_context_id,
        entry_surface="api_negociar_legacy",
        entrypoint=entrypoint,
        context_source="api_negociar_explicit",
    )
