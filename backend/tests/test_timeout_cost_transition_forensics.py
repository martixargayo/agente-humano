from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from scripts.forensics_timeout_cost_transition import build_report
from sessions.state import get_session_store, reset_session_store


def test_failed_timeout_attempt_records_forensic_transition_metadata() -> None:
    reset_session_store()
    get_session_store().clear()
    client = TestClient(app, raise_server_exceptions=False)

    bootstrap = client.post(
        "/api/optimizador/sessions/bootstrap",
        json={"user_id": "u_ft", "session_id": "s_ft"},
    )
    assert bootstrap.status_code == 200

    with patch("negociacion.optimizador.services.execute_turn_with_contract", side_effect=RuntimeError("Timeout writing to socket")):
        response = client.post(
            "/api/optimizador/sandbox/turn",
            json={
                "optimizer_session_id": "default",
                "user_id": "u_ft",
                "session_id": "s_ft",
                "message": "hola",
                "client_request_id": "req-ft-1",
                "logical_user_message_id": "lmsg-ft",
                "logical_attempt_index": 1,
            },
        )

    assert response.status_code == 500
    attempts = client.get("/api/optimizador/sessions/u_ft/s_ft/attempts").json()["items"]
    latest = attempts[-1]
    assert latest["error_category"] == "upstream_write_timeout"
    assert latest["error_id"].startswith("opt_turn_")
    assert "Timeout writing to socket" in latest["diagnostic"]
    assert latest["provider_calls_in_attempt"] == 0


def test_forensics_timeout_report_builds_pre_error_post_window() -> None:
    attempts = [
        {
            "backend_turn_attempt_id": "a1",
            "status": "success",
            "latest_turn_id": "t1",
            "logical_user_message_id": "l1",
            "logical_attempt_index": 1,
            "provider_calls_in_attempt": 4,
        },
        {
            "backend_turn_attempt_id": "a2",
            "status": "failed",
            "error_id": "opt_turn_017a88dff5",
            "error_category": "upstream_write_timeout",
            "failing_stage": "execute_turn_with_contract",
            "diagnostic": "Timeout writing to socket",
            "provider_calls_in_attempt": 4,
        },
        {
            "backend_turn_attempt_id": "a3",
            "status": "success",
            "latest_turn_id": "t2",
            "logical_user_message_id": "l1",
            "logical_attempt_index": 2,
            "provider_calls_in_attempt": 5,
        },
    ]
    turns = [
        {
            "turn_id": "t1",
            "turn_started_at": "2026-04-02T14:06:33+00:00",
            "final_status": "deliver",
            "provider_calls": [{"model": "gpt-5-nano", "call_subtype": "responses.create"}],
            "nodes": {"planner": {"input_summary": {"recent_dialogue_count": 3}, "prompt_artifacts": {"payload_chars": 1200, "payload_hash": "p1"}}},
        },
        {
            "turn_id": "t2",
            "turn_started_at": "2026-04-02T14:07:11+00:00",
            "final_status": "deliver",
            "provider_calls": [{"model": "gpt-5-nano", "call_subtype": "responses.create"}, {"model": "o4-mini", "call_subtype": "responses.create"}],
            "nodes": {"planner": {"input_summary": {"recent_dialogue_count": 7, "selected_memory_count": 5}, "prompt_artifacts": {"payload_chars": 42000, "payload_hash": "p2"}}},
        },
    ]
    csv_by_minute = {
        "2026-04-02T14:07:00+00:00": {"minute_utc": "2026-04-02T14:07:00+00:00", "input_text_tokens": "122899", "requests": "5"}
    }

    report = build_report(
        attempts=attempts,
        turns=turns,
        timeout_error_id="opt_turn_017a88dff5",
        csv_by_minute=csv_by_minute,
    )

    assert report["window"]["error_attempt"]["backend_turn_attempt_id"] == "a2"
    assert len(report["turn_rows"]) == 3
    post_row = report["turn_rows"][-1]
    assert post_row["csv_minute"] == "2026-04-02T14:07:00+00:00"
    assert post_row["csv_row"]["input_text_tokens"] == "122899"
