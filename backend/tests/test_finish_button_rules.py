from __future__ import annotations

from negociacion.nodes.phase_classifier_node import PhaseClassifierOutput
from negociacion.orchestration.finish_button_rules import evaluate_finish_button_triggers
from negociacion.orchestration.flow_config import apply_finish_button_state, apply_phase_classifier_output_to_state
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import NegotiationPhase, ThreadMode


def test_finish_button_rule_arms_on_formalizacion_phase():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)
    state.planner_state.current_phase = NegotiationPhase.formalizacion_del_acuerdo

    evaluation = evaluate_finish_button_triggers(state)

    assert evaluation.should_arm is True
    assert "phase_formalizacion_del_acuerdo" in evaluation.reasons


def test_finish_button_latch_stays_armed_after_phase_changes():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)

    apply_phase_classifier_output_to_state(
        state,
        PhaseClassifierOutput(
            schema_version="phase_classifier.v1",
            current_phase=NegotiationPhase.formalizacion_del_acuerdo,
        ),
    )
    apply_finish_button_state(state)
    assert state.ui_state.finish_button_armed is True

    apply_phase_classifier_output_to_state(
        state,
        PhaseClassifierOutput(
            schema_version="phase_classifier.v1",
            current_phase=NegotiationPhase.concesiones_y_ajuste_final,
        ),
    )
    apply_finish_button_state(state)

    assert state.ui_state.finish_button_armed is True
