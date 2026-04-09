from __future__ import annotations

from evaluacion.domains.conversacion_simple.adapter import ConversacionSimpleEvaluationAdapter
from evaluacion.domains.negotiation.adapter import NegotiationEvaluationAdapter
from sessions.state import SessionState


def _seed_history(state: SessionState) -> None:
    state.history = [
        {'role': 'user', 'content': 'hola'},
        {'role': 'assistant', 'content': 'buenas'},
    ]


def test_negotiation_adapter_delegates_bundle_building() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)
    state.world_state['negotiation_context'] = {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'}

    adapter = NegotiationEvaluationAdapter()
    bundle = adapter.build_feedback_input_bundle_v1(state=state, evaluation_id='e')

    assert bundle.domain_context.flow_id == 'negociacion'


def test_conversacion_simple_adapter_delegates_bundle_building() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)
    state.world_state['conversacion_simple_context'] = {'flow_id': 'conversacion_simple', 'context_id': 'baseline', 'context_version': '1.0.0'}

    adapter = ConversacionSimpleEvaluationAdapter()
    bundle = adapter.build_feedback_input_bundle_v1(state=state, evaluation_id='e')

    assert bundle.domain_context.flow_id == 'conversacion_simple'
