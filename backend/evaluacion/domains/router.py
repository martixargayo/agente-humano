from __future__ import annotations

from typing import Protocol

from sessions.state import SessionState

from conversacion_simple.contexts import read_bound_conversacion_simple_context_from_session
from evaluacion.contracts.models import DomainContext, FeedbackInputBundleV1, NegotiationDomainRubricV1
from evaluacion.domains.conversacion_simple import (
    ConversacionSimpleEvaluationAdapter,
    load_conversacion_simple_rubric_v1,
    resolve_conversacion_simple_evaluation_assets,
)
from evaluacion.domains.conversacion_simple.context_resolver import resolve_evaluation_context_from_session as resolve_cs_context
from evaluacion.domains.negotiation import NegotiationEvaluationAdapter, load_negotiation_rubric_v1, resolve_negotiation_evaluation_assets
from evaluacion.domains.negotiation.context_resolver import resolve_evaluation_context_from_session as resolve_neg_context
from negociacion.contexts import read_bound_context_from_session


class EvaluationDomainAdapter(Protocol):
    flow_id: str

    def build_feedback_input_bundle_v1(self, *, state: SessionState, evaluation_id: str) -> FeedbackInputBundleV1: ...


_ADAPTERS: dict[str, EvaluationDomainAdapter] = {
    'negociacion': NegotiationEvaluationAdapter(),
    'conversacion_simple': ConversacionSimpleEvaluationAdapter(),
}


def _world_state_has_negotiation_signal(state: SessionState) -> bool:
    ws = state.world_state if isinstance(state.world_state, dict) else {}
    return isinstance(ws.get('negotiation_canonical'), dict) or isinstance(ws.get('negotiation_canonical_traces'), list)


def _world_state_has_conversacion_simple_signal(state: SessionState) -> bool:
    ws = state.world_state if isinstance(state.world_state, dict) else {}
    return isinstance(ws.get('conversation_simple_canonical'), dict) or isinstance(ws.get('conversation_simple_canonical_traces'), list)


def resolve_flow_id_from_state(state: SessionState) -> tuple[str, str, bool]:
    bound_neg = read_bound_context_from_session(state)
    bound_cs = read_bound_conversacion_simple_context_from_session(state)

    if bound_neg is not None and bound_cs is not None:
        raise RuntimeError('evaluation_flow_conflict:negociacion+conversacion_simple')

    if bound_neg is not None:
        return 'negociacion', 'session_binding', False
    if bound_cs is not None:
        return 'conversacion_simple', 'session_binding', False

    neg_signal = _world_state_has_negotiation_signal(state)
    cs_signal = _world_state_has_conversacion_simple_signal(state)
    if neg_signal and cs_signal:
        raise RuntimeError('evaluation_flow_conflict:legacy_signals_multiple')
    if neg_signal:
        return 'negociacion', 'legacy_world_state_signal', True
    if cs_signal:
        return 'conversacion_simple', 'legacy_world_state_signal', True

    raise RuntimeError('evaluation_flow_resolution_error:no_binding_or_legacy_signal')


def build_feedback_input_bundle_v1(*, state: SessionState, evaluation_id: str) -> FeedbackInputBundleV1:
    flow_id, flow_resolution_source, fallback_used = resolve_flow_id_from_state(state)
    adapter = _ADAPTERS.get(flow_id)
    if adapter is None:
        raise RuntimeError(f'evaluation_unsupported_flow:{flow_id}')
    bundle = adapter.build_feedback_input_bundle_v1(state=state, evaluation_id=evaluation_id)
    # Router-level resolution source takes precedence; merge with inner source only if different
    inner_source = bundle.domain_context.resolution_source
    if inner_source and inner_source != flow_resolution_source:
        merged_source = f'{flow_resolution_source}→{inner_source}'
    else:
        merged_source = flow_resolution_source
    bundle.domain_context.resolution_source = merged_source
    bundle.domain_context.fallback_used = bool(bundle.domain_context.fallback_used or fallback_used)
    return bundle


def resolve_evaluation_assets(domain_context: DomainContext):
    if domain_context.flow_id == 'conversacion_simple':
        return resolve_conversacion_simple_evaluation_assets(domain_context)
    if domain_context.flow_id == 'negociacion':
        return resolve_negotiation_evaluation_assets(domain_context)
    if not domain_context.flow_id:
        raise RuntimeError('evaluation_assets_resolution_error:flow_id_missing')
    raise RuntimeError(f'evaluation_unsupported_flow:{domain_context.flow_id}')


def load_domain_rubric_v1(domain_context: DomainContext) -> NegotiationDomainRubricV1:
    if domain_context.flow_id == 'conversacion_simple':
        return load_conversacion_simple_rubric_v1(domain_context)
    if domain_context.flow_id == 'negociacion':
        return load_negotiation_rubric_v1(domain_context)
    if not domain_context.flow_id:
        raise RuntimeError('evaluation_rubric_loading_error:flow_id_missing')
    raise RuntimeError(f'evaluation_unsupported_flow:{domain_context.flow_id}')


def validate_session_context_precedence(*, state: SessionState, domain_context: DomainContext) -> None:
    if domain_context.flow_id == 'conversacion_simple':
        resolve_cs_context(state, domain_context)
        return
    resolve_neg_context(state, domain_context)
