from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from interfaz_usuario import services as interfaz_services
from scripts.forensics_context_skew_first_divergence import build_report


REPORT = build_report()


def _scenario(scenario_id: str) -> dict:
    for item in REPORT["scenarios"]:
        if item["scenario_id"] == scenario_id:
            return item
    raise AssertionError(f"scenario_not_found:{scenario_id}")


def test_clean_sessions_have_no_mismatch() -> None:
    clean_validacion = _scenario("clean_validacion")
    clean_sala = _scenario("clean_sala")

    assert clean_validacion["first_mismatch"] is None
    assert clean_sala["first_mismatch"] is None


def test_forced_skew_is_blocked_pre_execution() -> None:
    skew = _scenario("forced_skew_validacion_to_sala")
    assert skew["blocked"] is not None
    assert skew["blocked"]["blocked"] is True
    assert skew["first_mismatch"] is None


def test_forced_skew_does_not_reach_planner_or_executor_composition() -> None:
    skew = _scenario("forced_skew_validacion_to_sala")
    steps = {event["step"]: event for event in skew["events"]}
    assert "build_planner_input" not in steps
    assert "build_executor_input" not in steps


def test_forced_skew_does_not_emit_trace_context_meta() -> None:
    skew = _scenario("forced_skew_validacion_to_sala")
    assert all(event["step"] != "build_trace_context_meta" for event in skew["events"])


def test_runtime_surface_rejects_context_switch_same_session() -> None:
    payload = interfaz_services.ensure_session(user_id="u_surface_skew", session_id="s_surface_skew", context_id="validacion_multicontexto")
    assert payload["context_id"] == "validacion_multicontexto"

    try:
        interfaz_services.ensure_session(user_id="u_surface_skew", session_id="s_surface_skew", context_id="sala_reuniones")
        raise AssertionError("expected_http_409")
    except HTTPException as exc:
        assert exc.status_code == 409
