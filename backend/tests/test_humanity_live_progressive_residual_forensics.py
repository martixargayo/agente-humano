from __future__ import annotations

from scripts.forensics_humanity_live_progressive_residual import build_report


def test_live_forensics_runtime_mode_is_recorded():
    report = build_report()

    assert report["runtime_mode"] in {"openai_live", "fallback_no_api_key"}
    assert report["notes"]["live_runtime_attempted"] is True


def test_controlled_asymmetric_continuity_keeps_first_structural_diff_tracking():
    report = build_report()
    c_first = report["checks"]["C_first_structural_diff"]

    assert c_first is not None
    assert c_first["structural_first_diff"] in {
        "planner_recent_dialogue_len",
        "executor_recent_dialogue_len",
        "selected_memory_count",
    }


def test_baseline_clean_remains_without_early_structural_divergence():
    report = build_report()

    assert report["checks"]["A_first_structural_diff"] is None
