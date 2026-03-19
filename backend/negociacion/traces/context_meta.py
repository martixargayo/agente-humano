from __future__ import annotations

from sessions.state import SessionState

from ..contexts import read_bound_context_from_session, resolve_default_negotiation_context
from .models import TraceContextMeta


def build_trace_context_meta(*, state: SessionState, overrides_applied: bool = False) -> TraceContextMeta:
    bound = read_bound_context_from_session(state)
    if bound is None:
        resolved = resolve_default_negotiation_context()
        flow_id = resolved.flow_id
        context_id = resolved.context_id
        context_version = resolved.context_version
    else:
        flow_id = bound.flow_id
        context_id = bound.context_id
        context_version = bound.context_version

    return TraceContextMeta(
        flow_id=flow_id,
        context_id=context_id,
        context_version=context_version,
        official_context_used=True,
        context_scope='official_with_overrides' if overrides_applied else 'official',
    )
