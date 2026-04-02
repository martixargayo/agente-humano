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
from ..orchestration.context_errors import SessionContextConflictError


def resolve_optimizer_context_payload(*, context_id: str | None = None) -> dict[str, Any]:
    normalized = (context_id or '').strip() or None
    try:
        resolved = resolve_negotiation_context(normalized) if normalized is not None else resolve_default_negotiation_context()
    except NegotiationContextResolutionError as exc:
        raise ValueError(f"unsupported_context_id:{normalized}") from exc
    return {
        'flow_id': resolved.flow_id,
        'context_id': resolved.context_id,
        'context_version': resolved.context_version,
        'public_slug': resolved.public_slug,
        'resolution_source': resolved.resolution_source,
    }


def ensure_optimizer_session_context(*, state: SessionState, requested_context_id: str | None = None) -> dict[str, Any]:
    bound = ensure_session_context(state=state, requested_context_id=requested_context_id)
    return {
        'flow_id': bound.flow_id,
        'context_id': bound.context_id,
        'context_version': bound.context_version,
    }


def inherit_or_bind_sandbox_context(*, source_state: SessionState, target_state: SessionState, requested_context_id: str | None = None) -> dict[str, Any]:
    source_context = read_bound_context_from_session(source_state)
    if source_context is None:
        source_context = ensure_session_context(state=source_state)

    requested = (requested_context_id or '').strip() or None
    if requested is not None and requested != source_context.context_id:
        raise SessionContextConflictError(
            session_id=source_state.session_id,
            existing_context_id=source_context.context_id,
            requested_context_id=requested,
        )

    return ensure_optimizer_session_context(state=target_state, requested_context_id=source_context.context_id)
