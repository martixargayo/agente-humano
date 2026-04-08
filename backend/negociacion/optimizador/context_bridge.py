from __future__ import annotations

from typing import Any

from sessions.state import SessionState

from ..contexts import (
    NegotiationContextResolutionError,
    ensure_session_context,
    read_bound_context_from_session,
    resolve_default_negotiation_context,
    resolve_negotiation_context,
)
from conversacion_simple.contexts import (
    ConversationSimpleContextResolutionError,
    ensure_conversacion_simple_session_context,
    read_bound_conversacion_simple_context_from_session,
    resolve_conversacion_simple_context,
    resolve_default_conversacion_simple_context,
)
from ..orchestration.context_errors import SessionContextConflictError


def resolve_optimizer_context_payload(*, context_id: str | None = None) -> dict[str, Any]:
    normalized = (context_id or '').strip() or None
    try:
        resolved = resolve_negotiation_context(normalized) if normalized is not None else resolve_default_negotiation_context()
    except NegotiationContextResolutionError:
        try:
            resolved = resolve_conversacion_simple_context(normalized) if normalized is not None else resolve_default_conversacion_simple_context()
        except ConversationSimpleContextResolutionError as exc:
            raise ValueError(f"unsupported_context_id:{normalized}") from exc
    return {
        'flow_id': resolved.flow_id,
        'context_id': resolved.context_id,
        'context_version': resolved.context_version,
        'public_slug': resolved.public_slug,
        'resolution_source': resolved.resolution_source,
    }


def ensure_optimizer_session_context(
    *,
    state: SessionState,
    requested_context_id: str | None = None,
    requested_flow_id: str | None = None,
) -> dict[str, Any]:
    normalized = (requested_context_id or "").strip() or None
    normalized_flow = (requested_flow_id or "").strip() or None
    bound_neg = read_bound_context_from_session(state)
    bound_cs = read_bound_conversacion_simple_context_from_session(state)
    if bound_neg is not None:
        if bound_cs is not None:
            raise ValueError("session_has_mixed_flow_bindings")
        if normalized_flow is not None and normalized_flow != "negociacion":
            raise SessionContextConflictError(
                session_id=state.session_id,
                existing_context_id=bound_neg.context_id,
                requested_context_id=normalized or normalized_flow,
            )
        bound = ensure_session_context(state=state, requested_context_id=normalized)
        return {
            'flow_id': bound.flow_id,
            'context_id': bound.context_id,
            'context_version': bound.context_version,
        }
    if bound_cs is not None:
        if normalized_flow is not None and normalized_flow != "conversacion_simple":
            raise SessionContextConflictError(
                session_id=state.session_id,
                existing_context_id=bound_cs.context_id,
                requested_context_id=normalized or normalized_flow,
            )
        bound = ensure_conversacion_simple_session_context(state=state, requested_context_id=normalized)
        return {
            'flow_id': bound.flow_id,
            'context_id': bound.context_id,
            'context_version': bound.context_version,
        }
    if normalized_flow == "conversacion_simple":
        try:
            resolve_conversacion_simple_context(normalized) if normalized else resolve_default_conversacion_simple_context()
        except ConversationSimpleContextResolutionError as exc:
            raise ValueError(f"unsupported_context_id:{normalized}") from exc
        bound = ensure_conversacion_simple_session_context(state=state, requested_context_id=normalized)
    elif normalized_flow == "negociacion":
        try:
            resolve_negotiation_context(normalized) if normalized else resolve_default_negotiation_context()
        except NegotiationContextResolutionError as exc:
            raise ValueError(f"unsupported_context_id:{normalized}") from exc
        bound = ensure_session_context(state=state, requested_context_id=normalized)
    else:
        try:
            resolve_negotiation_context(normalized) if normalized else resolve_default_negotiation_context()
            bound = ensure_session_context(state=state, requested_context_id=normalized)
        except NegotiationContextResolutionError:
            bound = ensure_conversacion_simple_session_context(state=state, requested_context_id=normalized)
    return {
        'flow_id': bound.flow_id,
        'context_id': bound.context_id,
        'context_version': bound.context_version,
    }


def inherit_or_bind_sandbox_context(*, source_state: SessionState, target_state: SessionState, requested_context_id: str | None = None) -> dict[str, Any]:
    source_context = read_bound_context_from_session(source_state)
    source_cs_context = read_bound_conversacion_simple_context_from_session(source_state)
    if source_context is None and source_cs_context is None:
        source_context = ensure_session_context(state=source_state)
    if source_context is not None and source_cs_context is not None:
        raise ValueError("session_has_mixed_flow_bindings")

    requested = (requested_context_id or '').strip() or None
    if source_context is not None:
        if requested is not None and requested != source_context.context_id:
            raise SessionContextConflictError(
                session_id=source_state.session_id,
                existing_context_id=source_context.context_id,
                requested_context_id=requested,
            )
        return ensure_optimizer_session_context(state=target_state, requested_context_id=source_context.context_id)

    assert source_cs_context is not None
    if requested is not None and requested != source_cs_context.context_id:
        raise SessionContextConflictError(
            session_id=source_state.session_id,
            existing_context_id=source_cs_context.context_id,
            requested_context_id=requested,
        )
    return ensure_optimizer_session_context(state=target_state, requested_context_id=source_cs_context.context_id)
