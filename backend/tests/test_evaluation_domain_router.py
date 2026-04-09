from __future__ import annotations

import pytest

from evaluacion.contracts.models import DomainContext
from evaluacion.domains.router import build_feedback_input_bundle_v1, resolve_flow_id_from_state
from sessions.state import SessionState



def _seed_history(state: SessionState) -> None:
    state.history = [
        {'role': 'user', 'content': 'hola'},
        {'role': 'assistant', 'content': 'buenas'},
    ]


def test_router_prefers_negotiation_session_binding() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)
    state.world_state['negotiation_context'] = {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'}

    flow_id, source, fallback = resolve_flow_id_from_state(state)

    assert flow_id == 'negociacion'
    assert source == 'session_binding'
    assert fallback is False


def test_router_prefers_conversacion_simple_session_binding() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)
    state.world_state['conversacion_simple_context'] = {'flow_id': 'conversacion_simple', 'context_id': 'baseline', 'context_version': '1.0.0'}

    bundle = build_feedback_input_bundle_v1(state=state, evaluation_id='eval-cs')

    assert bundle.domain_context.flow_id == 'conversacion_simple'
    assert bundle.domain_context.context_id == 'baseline'
    assert bundle.domain_context.fallback_used is False


def test_router_rejects_conflicting_flow_bindings() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)
    state.world_state['negotiation_context'] = {'flow_id': 'negociacion', 'context_id': 'baseline_current', 'context_version': '1.0.0'}
    state.world_state['conversacion_simple_context'] = {'flow_id': 'conversacion_simple', 'context_id': 'baseline', 'context_version': '1.0.0'}

    with pytest.raises(RuntimeError, match='evaluation_flow_conflict'):
        resolve_flow_id_from_state(state)


def test_router_rejects_unknown_legacy_state_without_signals() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)

    with pytest.raises(RuntimeError, match='evaluation_flow_resolution_error'):
        resolve_flow_id_from_state(state)


def test_router_uses_legacy_negotiation_signal_when_no_binding() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)
    state.world_state['negotiation_canonical'] = {'planner_state': {}}

    flow_id, source, fallback = resolve_flow_id_from_state(state)

    assert flow_id == 'negociacion'
    assert source == 'legacy_world_state_signal'
    assert fallback is True


def test_router_rejects_ambiguous_legacy_signals() -> None:
    state = SessionState(user_id='u', session_id='s')
    _seed_history(state)
    state.world_state['negotiation_canonical'] = {'planner_state': {}}
    state.world_state['conversation_simple_canonical'] = {'conversation_state': {}}

    with pytest.raises(RuntimeError, match='legacy_signals_multiple'):
        resolve_flow_id_from_state(state)


def test_router_assets_rejects_missing_flow_id() -> None:
    """Verify that resolve_evaluation_assets fails explicitly with flow_id=None, not silently defaulting"""
    from evaluacion.domains.router import resolve_evaluation_assets

    dc = DomainContext(domain='conversacion_simple', flow_id=None, context_id='x')

    with pytest.raises(RuntimeError, match='evaluation_assets_resolution_error:flow_id_missing'):
        resolve_evaluation_assets(dc)


def test_router_rubric_rejects_missing_flow_id() -> None:
    """Verify that load_domain_rubric_v1 fails explicitly with flow_id=None"""
    from evaluacion.domains.router import load_domain_rubric_v1

    dc = DomainContext(domain='conversacion_simple', flow_id=None, context_id='x')

    with pytest.raises(RuntimeError, match='evaluation_rubric_loading_error:flow_id_missing'):
        load_domain_rubric_v1(dc)
