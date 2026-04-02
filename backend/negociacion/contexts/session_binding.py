from __future__ import annotations

from sessions.state import SessionState

from ..orchestration.context_errors import SessionContextConflictError
from .models import BoundNegotiationContext, ResolvedNegotiationContext
from .resolver import resolve_default_negotiation_context, resolve_negotiation_context

NEGOTIATION_CONTEXT_WORLD_STATE_KEY = "negotiation_context"


def read_bound_context_from_session(state: SessionState) -> BoundNegotiationContext | None:
    world_state = state.world_state if isinstance(state.world_state, dict) else {}
    raw = world_state.get(NEGOTIATION_CONTEXT_WORLD_STATE_KEY)
    if not isinstance(raw, dict):
        return None

    flow_id = raw.get("flow_id")
    context_id = raw.get("context_id")
    context_version = raw.get("context_version")
    if not all(isinstance(value, str) and value.strip() for value in (flow_id, context_id, context_version)):
        return None

    return BoundNegotiationContext(
        flow_id=flow_id.strip(),
        context_id=context_id.strip(),
        context_version=context_version.strip(),
    )


def bind_context_to_session(*, state: SessionState, context: ResolvedNegotiationContext) -> BoundNegotiationContext:
    bound = BoundNegotiationContext(
        flow_id=context.flow_id,
        context_id=context.context_id,
        context_version=context.context_version,
    )
    if not isinstance(state.world_state, dict):
        state.world_state = {}
    state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY] = bound.model_dump(mode="json")
    return bound


def ensure_session_context(*, state: SessionState, requested_context_id: str | None = None) -> BoundNegotiationContext:
    existing = read_bound_context_from_session(state)
    normalized_requested = (requested_context_id or "").strip() or None

    if existing is not None:
        if normalized_requested is not None and normalized_requested != existing.context_id:
            raise SessionContextConflictError(
                session_id=state.session_id,
                existing_context_id=existing.context_id,
                requested_context_id=normalized_requested,
            )
        return existing

    resolved = (
        resolve_negotiation_context(normalized_requested)
        if normalized_requested is not None
        else resolve_default_negotiation_context()
    )
    return bind_context_to_session(state=state, context=resolved)
