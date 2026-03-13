from __future__ import annotations

from scripts.forensics_humanity_residual_planner_executor import build_report


def test_progressive_reuse_produces_divergence_and_boundary_auto_reset_is_applied():
    report = build_report()

    first_diff = report["checks"]["s2_first_progressive_diff"]
    assert first_diff is not None
    assert first_diff["first_diff"] in {"planner_recent_dialogue_len", "executor_recent_dialogue_len", "planner_selected_memory_count"}
    assert report["checks"]["boundary_auto_reset_applied"] is True


def test_both_fresh_or_both_reuse_keep_surface_symmetry_under_same_pattern():
    report = build_report()

    fresh_eps = report["scenarios"]["both_fresh_per_episode"]
    reuse_eps = report["scenarios"]["both_reuse_control"]

    for ep in fresh_eps + reuse_eps:
        o_last = ep["optimizer"]["turns"][-1]
        i_last = ep["interfaz"]["turns"][-1]
        assert o_last["planner_recent_dialogue_len"] == i_last["planner_recent_dialogue_len"]
        assert o_last["executor_recent_dialogue_len"] == i_last["executor_recent_dialogue_len"]
