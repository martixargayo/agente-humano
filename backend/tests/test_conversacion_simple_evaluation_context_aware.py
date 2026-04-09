from __future__ import annotations

import pytest

from evaluacion.contracts.models import DomainContext
from evaluacion.domains.conversacion_simple.context_resolver import resolve_evaluation_context_from_session
from evaluacion.domains.router import build_feedback_input_bundle_v1
from sessions.state import SessionState


def _seed_history(state: SessionState) -> None:
    state.history = [
        {'role': 'user', 'content': 'hola'},
        {'role': 'assistant', 'content': 'buenas, ¿qué necesitas?'},
        {'role': 'user', 'content': 'quiero organizar la reunión'},
        {'role': 'assistant', 'content': 'perfecto, cuéntame el contexto'},
    ]


def test_conversacion_simple_bundle_uses_session_binding_and_context_metadata() -> None:
    state = SessionState(user_id='u_cs', session_id='s_cs')
    _seed_history(state)
    state.world_state['conversacion_simple_context'] = {
        'flow_id': 'conversacion_simple',
        'context_id': 'negociacion_sala_reuniones',
        'context_version': '1.0.0',
    }

    bundle = build_feedback_input_bundle_v1(state=state, evaluation_id='eval-cs')

    assert bundle.domain_context.domain == 'conversacion_simple'
    assert bundle.domain_context.flow_id == 'conversacion_simple'
    assert bundle.domain_context.context_id == 'negociacion_sala_reuniones'
    assert bundle.domain_context.resolution_source == 'session_binding'
    assert bundle.domain_context.fallback_used is False


def test_conversacion_simple_context_precedence_rejects_conflicting_domain_context() -> None:
    state = SessionState(user_id='u_cs', session_id='s_cs')
    _seed_history(state)
    state.world_state['conversacion_simple_context'] = {
        'flow_id': 'conversacion_simple',
        'context_id': 'baseline',
        'context_version': '1.0.0',
    }

    with pytest.raises(RuntimeError, match='evaluation_context_conflict'):
        resolve_evaluation_context_from_session(
            state,
            DomainContext(domain='conversacion_simple', flow_id='conversacion_simple', context_id='negociacion_sala_reuniones', context_version='1.0.0'),
        )
