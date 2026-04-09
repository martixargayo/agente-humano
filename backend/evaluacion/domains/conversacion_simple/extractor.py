from __future__ import annotations

from sessions.state import SessionState

from evaluacion.contracts.models import (
    DerivedFacts,
    DomainContext,
    FeedbackInputBundleV1,
    SessionRef,
    TraceDigest,
)
from evaluacion.domains.common_extractor import build_conversation_stats, pair_turns_from_history

from .context_resolver import resolve_evaluation_context_from_session


def _build_domain_context(state: SessionState) -> DomainContext:
    canonical = state.world_state.get('conversation_simple_canonical', {}) if isinstance(state.world_state, dict) else {}
    conversation_state = canonical.get('conversation_state', {}) if isinstance(canonical, dict) else {}
    phase = conversation_state.get('phase') if isinstance(conversation_state, dict) else None
    evaluation_context = resolve_evaluation_context_from_session(state)
    return DomainContext(
        domain='conversacion_simple',
        flow_id=evaluation_context.flow_id,
        context_id=evaluation_context.context_id,
        context_version=evaluation_context.context_version,
        resolution_source=evaluation_context.resolution_source,
        fallback_used=evaluation_context.fallback_used,
        final_phase=str(phase) if phase else None,
        finish_button_was_armed=False,
    )


def _build_derived_facts(turns):
    question_turns: list[int] = []
    close_signals = 0
    offer_signals = 0
    blocker_signals = 0

    for turn in turns:
        u = turn.user_text.lower()
        if '?' in turn.user_text:
            question_turns.append(turn.turn_index)
        if any(token in u for token in ('cerr', 'acuerdo', 'trato', 'hoy')):
            close_signals += 1
        if any(token in u for token in ('precio', 'ofert', 'euros', 'rebaja')):
            offer_signals += 1
        if any(token in u for token in ('no puedo', 'imposible', 'bloque', 'difícil')):
            blocker_signals += 1

    return DerivedFacts(
        question_turn_indexes=question_turns,
        close_signals_count=close_signals,
        offer_signals_count=offer_signals,
        blocker_signals_count=blocker_signals,
    )


def _build_trace_digest(state: SessionState) -> TraceDigest:
    traces_key = 'conversation_simple_canonical_traces'
    raw_traces = state.world_state.get(traces_key, []) if isinstance(state.world_state, dict) else []
    traces = raw_traces if isinstance(raw_traces, list) else []

    guardrail_events = 0
    for trace in traces:
        if isinstance(trace, dict) and trace.get('guardrails_triggered'):
            guardrail_events += 1
    return TraceDigest(trace_count=len(traces), guardrail_events_count=guardrail_events)


def build_feedback_input_bundle_v1(*, state: SessionState, evaluation_id: str) -> FeedbackInputBundleV1:
    turns = pair_turns_from_history(state)
    return FeedbackInputBundleV1(
        schema_version='feedback_input_bundle.v1',
        evaluation_id=evaluation_id,
        session_ref=SessionRef(user_id=state.user_id, session_id=state.session_id),
        conversation={'turns': turns},
        conversation_stats=build_conversation_stats(turns),
        domain_context=_build_domain_context(state),
        derived_facts=_build_derived_facts(turns),
        trace_digest=_build_trace_digest(state),
    )
