from __future__ import annotations

from scripts.forensics_effective_context_parity import build_report


def test_clean_surface_payload_parity_without_overrides() -> None:
    report = build_report()
    assert report["global_checks"]["all_node_payloads_equal"] is True
    assert report["global_checks"]["all_memory_working_equal"] is True
    assert report["global_checks"]["all_planner_state_equal"] is True
    assert report["global_checks"]["all_negotiation_state_equal"] is True
    assert report["first_payload_divergence"] is None


def test_hidden_continuity_is_first_real_divergence_point() -> None:
    report = build_report()
    skew = report["hidden_continuity_skew"]
    assert skew["first_divergence"]["node"] == "memory"
    assert skew["first_divergence"]["path"] == "recent_dialogue_short.length"
    assert skew["node_comparison"]["memory"]["recent_dialogue_len_optimizer"] > skew["node_comparison"]["memory"]["recent_dialogue_len_interfaz"]
