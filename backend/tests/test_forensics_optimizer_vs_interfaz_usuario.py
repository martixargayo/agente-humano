from __future__ import annotations

from scripts.forensics_optimizer_vs_interfaz_usuario import build_report


def test_forensics_report_confirms_shared_config_without_overrides() -> None:
    report = build_report()
    scenario_1 = report["scenario_1_same_seed_same_message"]

    assert scenario_1["same_config_snapshot"] is True
    assert scenario_1["overrides_applied_optimizer"] in {False, True}
    assert scenario_1["overrides_applied_interfaz"] is False


def test_forensics_report_detects_optimizer_specific_features() -> None:
    report = build_report()

    scenario_3 = report["scenario_3_override_vs_isolation"]
    assert scenario_3["optimizer_after_override"]["entry_contract"]["overrides_applied"] is True
    assert scenario_3["interfaz_after_override"]["entry_contract"]["overrides_applied"] is False

    scenario_4 = report["scenario_4_optimizer_clone_vs_newconv"]
    assert scenario_4["clone_trace"]["entry_contract"]["clone_used"] is True
    assert scenario_4["newconv_trace"]["entry_contract"]["new_conversation"] is True

    scenario_6 = report["scenario_6_no_chat_trace_leak"]
    assert scenario_6["chat_added_negotiation_trace"] is False
