from __future__ import annotations

from scripts.forensics_humanity_progressive_intra_negotiation import build_report


def test_clean_continuous_baseline_shows_no_cross_surface_first_divergence():
    report = build_report()
    assert report["checks"]["A_first_divergence"] is None


def test_hidden_residual_shows_early_context_skew_and_progressive_rigidity_signal():
    report = build_report()
    c_first = report["checks"]["C_first_divergence"]

    assert c_first is not None
    assert c_first["first_diff"] in {"planner_recent_dialogue_len", "executor_recent_dialogue_len"}
    assert report["checks"]["C_positive_gap_turns"]


def test_ablation_clamp_removes_progressive_rigidity_gap():
    report = build_report()

    assert report["checks"]["D_positive_gap_turns"] == []
    assert report["checks"]["C_positive_gap_turns"] != []
