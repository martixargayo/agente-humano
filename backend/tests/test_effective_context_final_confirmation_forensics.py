from __future__ import annotations

from scripts.forensics_effective_context_final_confirmation import build_report


def test_usage_pattern_explains_asymmetry_and_fresh_sessions_restore_parity():
    report = build_report()
    asym = report["scenarios"]["usage_pattern_asymmetry"]
    clean = report["scenarios"]["both_fresh_control"]

    assert asym["interfaz_contaminated_first_turns"] > asym["optimizer_contaminated_first_turns"]
    assert clean["interfaz_contaminated_first_turns"] == 0
    assert clean["optimizer_contaminated_first_turns"] == 0
    assert report["conclusion_checks"]["asymmetry_exists_under_usage_pattern"] is True
    assert report["conclusion_checks"]["parity_recovers_when_both_fresh"] is True
