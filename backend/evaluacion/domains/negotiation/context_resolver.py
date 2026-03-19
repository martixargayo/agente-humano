from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from sessions.state import SessionState

from negociacion.contexts import read_bound_context_from_session, resolve_default_negotiation_context, resolve_negotiation_context

from evaluacion.contracts.models import DomainContext


class NegotiationEvaluationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    context_id: str
    context_version: str
    resolution_source: str


def resolve_evaluation_context_from_domain_context(domain_context: DomainContext | None) -> NegotiationEvaluationContext:
    if domain_context is not None and domain_context.context_id:
        resolved = resolve_negotiation_context(domain_context.context_id)
        return NegotiationEvaluationContext(
            flow_id=domain_context.flow_id or resolved.flow_id,
            context_id=resolved.context_id,
            context_version=domain_context.context_version or resolved.context_version,
            resolution_source='bundle_domain_context',
        )

    resolved = resolve_default_negotiation_context()
    return NegotiationEvaluationContext(
        flow_id=resolved.flow_id,
        context_id=resolved.context_id,
        context_version=resolved.context_version,
        resolution_source='default_baseline',
    )


def resolve_evaluation_context_from_session(state: SessionState) -> NegotiationEvaluationContext:
    bound = read_bound_context_from_session(state)
    if bound is not None:
        return NegotiationEvaluationContext(
            flow_id=bound.flow_id,
            context_id=bound.context_id,
            context_version=bound.context_version,
            resolution_source='session_binding',
        )

    resolved = resolve_default_negotiation_context()
    return NegotiationEvaluationContext(
        flow_id=resolved.flow_id,
        context_id=resolved.context_id,
        context_version=resolved.context_version,
        resolution_source='legacy_default_baseline',
    )
