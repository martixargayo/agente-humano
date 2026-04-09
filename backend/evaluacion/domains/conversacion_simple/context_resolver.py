from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from sessions.state import SessionState

from conversacion_simple.contexts import (
    read_bound_conversacion_simple_context_from_session,
    resolve_conversacion_simple_context,
    resolve_default_conversacion_simple_context,
)

from evaluacion.contracts.models import DomainContext


class ConversationSimpleEvaluationContext(BaseModel):
    model_config = ConfigDict(extra='forbid')

    flow_id: str
    context_id: str
    context_version: str
    resolution_source: str
    fallback_used: bool = False


def _resolve_from_domain_context(domain_context: DomainContext) -> ConversationSimpleEvaluationContext:
    if domain_context.flow_id and domain_context.flow_id != 'conversacion_simple':
        raise RuntimeError(f"evaluation_flow_context_mismatch:conversacion_simple:{domain_context.flow_id}")
    resolved = resolve_conversacion_simple_context(domain_context.context_id)
    return ConversationSimpleEvaluationContext(
        flow_id=resolved.flow_id,
        context_id=resolved.context_id,
        context_version=domain_context.context_version or resolved.context_version,
        resolution_source='bundle_domain_context',
        fallback_used=False,
    )


def resolve_evaluation_context_from_domain_context(domain_context: DomainContext | None) -> ConversationSimpleEvaluationContext:
    if domain_context is not None and domain_context.context_id:
        return _resolve_from_domain_context(domain_context)

    resolved = resolve_default_conversacion_simple_context()
    return ConversationSimpleEvaluationContext(
        flow_id=resolved.flow_id,
        context_id=resolved.context_id,
        context_version=resolved.context_version,
        resolution_source='default_baseline',
        fallback_used=True,
    )


def resolve_evaluation_context_from_session(
    state: SessionState,
    domain_context: DomainContext | None = None,
) -> ConversationSimpleEvaluationContext:
    bound = read_bound_conversacion_simple_context_from_session(state)
    explicit = domain_context if (domain_context is not None and domain_context.context_id) else None

    if bound is not None:
        if explicit is not None:
            if explicit.flow_id and explicit.flow_id != bound.flow_id:
                raise RuntimeError(f"evaluation_flow_context_conflict:{bound.flow_id}:{explicit.flow_id}")
            if explicit.context_id != bound.context_id:
                raise RuntimeError(f"evaluation_context_conflict:{bound.context_id}:{explicit.context_id}")
        return ConversationSimpleEvaluationContext(
            flow_id=bound.flow_id,
            context_id=bound.context_id,
            context_version=bound.context_version,
            resolution_source='session_binding',
            fallback_used=False,
        )

    if explicit is not None:
        return _resolve_from_domain_context(explicit)

    resolved = resolve_default_conversacion_simple_context()
    return ConversationSimpleEvaluationContext(
        flow_id=resolved.flow_id,
        context_id=resolved.context_id,
        context_version=resolved.context_version,
        resolution_source='legacy_default_baseline',
        fallback_used=True,
    )
