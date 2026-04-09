from __future__ import annotations

from evaluacion.domains.router import build_feedback_input_bundle_v1
from sessions.state import SessionState


def _seed_history(state: SessionState) -> None:
    state.history = [
        {'role': 'user', 'content': 'hola'},
        {'role': 'assistant', 'content': 'buenas'},
    ]


def test_multiflow_context_isolation_between_sessions() -> None:
    neg = SessionState(user_id='u_neg', session_id='s_neg')
    _seed_history(neg)
    neg.world_state['negotiation_context'] = {'flow_id': 'negociacion', 'context_id': 'sala_reuniones', 'context_version': '1.0.0'}

    cs = SessionState(user_id='u_cs', session_id='s_cs')
    _seed_history(cs)
    cs.world_state['conversacion_simple_context'] = {'flow_id': 'conversacion_simple', 'context_id': 'baseline', 'context_version': '1.0.0'}

    neg_bundle = build_feedback_input_bundle_v1(state=neg, evaluation_id='eval-neg')
    cs_bundle = build_feedback_input_bundle_v1(state=cs, evaluation_id='eval-cs')

    assert neg_bundle.domain_context.flow_id == 'negociacion'
    assert neg_bundle.domain_context.context_id == 'sala_reuniones'
    assert cs_bundle.domain_context.flow_id == 'conversacion_simple'
    assert cs_bundle.domain_context.context_id == 'baseline'
    assert neg_bundle.domain_context.context_id != cs_bundle.domain_context.context_id
