from __future__ import annotations

import pytest

from evaluacion.contracts.models import DomainContext
from evaluacion.domains.conversacion_simple.context_resolver import resolve_evaluation_context_from_session as resolve_cs_context
from evaluacion.domains.negotiation.context_resolver import resolve_evaluation_context_from_session as resolve_neg_context
from sessions.state import SessionState


def test_negotiation_precedence_binding_plus_matching_domain_context_ok() -> None:
    state = SessionState(user_id='u', session_id='s')
    state.world_state['negotiation_context'] = {'flow_id': 'negociacion', 'context_id': 'sala_reuniones', 'context_version': '1.0.0'}

    resolved = resolve_neg_context(
        state,
        DomainContext(domain='negociacion', flow_id='negociacion', context_id='sala_reuniones', context_version='1.0.0'),
    )

    assert resolved.context_id == 'sala_reuniones'
    assert resolved.resolution_source == 'session_binding'
    assert resolved.fallback_used is False


def test_negotiation_precedence_binding_plus_conflicting_domain_context_fails() -> None:
    state = SessionState(user_id='u', session_id='s')
    state.world_state['negotiation_context'] = {'flow_id': 'negociacion', 'context_id': 'sala_reuniones', 'context_version': '1.0.0'}

    with pytest.raises(RuntimeError, match='evaluation_context_conflict'):
        resolve_neg_context(
            state,
            DomainContext(domain='negociacion', flow_id='negociacion', context_id='baseline_current', context_version='1.0.0'),
        )


def test_negotiation_no_binding_explicit_context_ok() -> None:
    state = SessionState(user_id='u', session_id='s')

    resolved = resolve_neg_context(
        state,
        DomainContext(domain='negociacion', flow_id='negociacion', context_id='sala_reuniones', context_version='1.0.0'),
    )

    assert resolved.context_id == 'sala_reuniones'
    assert resolved.resolution_source == 'bundle_domain_context'


def test_negotiation_no_binding_no_domain_context_uses_default() -> None:
    state = SessionState(user_id='u', session_id='s')

    resolved = resolve_neg_context(state)

    assert resolved.context_id == 'baseline_current'
    assert resolved.fallback_used is True


def test_conversacion_simple_precedence_binding_plus_matching_domain_context_ok() -> None:
    state = SessionState(user_id='u', session_id='s')
    state.world_state['conversacion_simple_context'] = {'flow_id': 'conversacion_simple', 'context_id': 'baseline', 'context_version': '1.0.0'}

    resolved = resolve_cs_context(
        state,
        DomainContext(domain='conversacion_simple', flow_id='conversacion_simple', context_id='baseline', context_version='1.0.0'),
    )

    assert resolved.context_id == 'baseline'
    assert resolved.resolution_source == 'session_binding'
    assert resolved.fallback_used is False


def test_conversacion_simple_precedence_binding_plus_conflicting_domain_context_fails() -> None:
    state = SessionState(user_id='u', session_id='s')
    state.world_state['conversacion_simple_context'] = {'flow_id': 'conversacion_simple', 'context_id': 'baseline', 'context_version': '1.0.0'}

    with pytest.raises(RuntimeError, match='evaluation_context_conflict'):
        resolve_cs_context(
            state,
            DomainContext(domain='conversacion_simple', flow_id='conversacion_simple', context_id='negociacion_sala_reuniones', context_version='1.0.0'),
        )


def test_conversacion_simple_no_binding_explicit_context_ok() -> None:
    state = SessionState(user_id='u', session_id='s')

    resolved = resolve_cs_context(
        state,
        DomainContext(domain='conversacion_simple', flow_id='conversacion_simple', context_id='negociacion_sala_reuniones', context_version='1.0.0'),
    )

    assert resolved.context_id == 'negociacion_sala_reuniones'
    assert resolved.resolution_source == 'bundle_domain_context'


def test_conversacion_simple_no_binding_no_domain_context_uses_default() -> None:
    state = SessionState(user_id='u', session_id='s')

    resolved = resolve_cs_context(state)

    assert resolved.context_id == 'baseline'
    assert resolved.fallback_used is True
