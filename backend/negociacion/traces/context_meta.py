from __future__ import annotations

from typing import TYPE_CHECKING

from sessions.state import SessionState

from ..contexts import read_bound_context_from_session, resolve_default_negotiation_context
from .models import TraceContextMeta

if TYPE_CHECKING:
    from ..orchestration.turn_context_validator import ValidatedTurnContext


def build_trace_context_meta(
    *,
    state: SessionState,
    overrides_applied: bool = False,
    validated_context: "ValidatedTurnContext | None" = None,
) -> TraceContextMeta:
    if validated_context is not None:
        effective_context_id = validated_context.effective_context_id
        session_bound_context_id = validated_context.session_bound_context_id
        config_context_id = validated_context.config_context_id
        trace_context_id = validated_context.trace_context_id
        context_version = validated_context.context_version
        reason_codes = validated_context.reason_codes
        context_source = validated_context.context_source
        execution_mode = validated_context.execution_mode
        mismatch = not (effective_context_id == session_bound_context_id == config_context_id == trace_context_id)
        return TraceContextMeta(
            flow_id=None,
            context_id=trace_context_id,
            context_version=context_version,
            official_context_used=True,
            context_scope='official_with_overrides' if overrides_applied else 'official',
            effective_context_id=effective_context_id,
            session_bound_context_id=session_bound_context_id,
            config_context_id=config_context_id,
            mismatch_detected=mismatch,
            mismatch_reason_code=None if not mismatch else "context_contract_mismatch",
            context_reason_codes=[str(code) for code in reason_codes],
            context_source=context_source,
            execution_mode=execution_mode,
        )

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
        effective_context_id=context_id,
        session_bound_context_id=context_id,
        config_context_id=context_id,
        mismatch_detected=False,
        mismatch_reason_code=None,
        context_reason_codes=["ctx_precheck_unavailable"],
        context_source="implicit_state_fallback",
        execution_mode="unknown",
    )
