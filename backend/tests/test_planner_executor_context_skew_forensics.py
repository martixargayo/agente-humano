from __future__ import annotations

from scripts.forensics_planner_executor_context_skew import build_report


def test_runtime_blocks_planner_goal_skew_even_if_injected_in_interfaz():
    report = build_report()
    scenario = report["scenarios"]["injected_planner_state_skew_interfaz_runtime"]

    assert scenario["first_divergence"] is None
    assert scenario["reply_optimizer"] == scenario["reply_interfaz"]


def test_legacy_emulation_reproduces_old_planner_state_goal_divergence():
    report = build_report()
    scenario = report["scenarios"]["injected_planner_state_skew_interfaz_legacy_emulation"]

    assert scenario["first_divergence"] == {"node": "planner", "path": "planner_state.current_turn_goal"}
    assert scenario["reply_optimizer"].startswith("Resumen del acuerdo")
    assert scenario["reply_interfaz"].startswith("Propuesta:")


def test_shared_phase_transition_keeps_parity_without_injected_skew():
    report = build_report()
    scenario = report["scenarios"]["phase_transition_shared_sessions"]

    assert scenario["first_divergence"] is None
    assert scenario["reply_optimizer"] == scenario["reply_interfaz"]
