from __future__ import annotations

from datetime import datetime, timezone

from negotiation.telemetry.live_trace import build_trace_event
from state import SessionState


def test_build_trace_event_includes_vnext_timing_and_llm_calls(monkeypatch):
    monkeypatch.setenv("TRACE_LEVEL", "2")
    monkeypatch.setenv("TRACE_INCLUDE_INTERNALS", "1")

    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = {
        "turn": 1,
        "t_turn_start": 1.0,
        "t_before_graph": 1.1,
        "t_after_graph": 1.4,
        "t_reply_saved": 1.5,
        "t_summary_enqueued": 1.9,
        "trace_runtime": {
            "nodes": {
                "world_updater": {"total_ms": 10, "gates_ms": 2, "normalize_merge_diff_ms": 3, "llm_ms": 5, "entered": True, "skipped": False},
                "belief_updater": {"total_ms": 11, "gates_ms": 1, "normalize_merge_diff_ms": 4, "llm_ms": 0, "entered": True, "skipped": False},
                "policy_progress": {"total_ms": 12, "gates_ms": 0, "normalize_merge_diff_ms": 2, "llm_ms": 0, "entered": True, "skipped": False},
                "phase_policy_planner": {"total_ms": 13, "gates_ms": 2, "normalize_merge_diff_ms": 1, "llm_ms": 10, "entered": True, "skipped": False},
                "progress_updater": {"total_ms": 14, "gates_ms": 0, "normalize_merge_diff_ms": 2, "llm_ms": 0, "entered": True, "skipped": False},
                "executor": {"total_ms": 15, "gates_ms": 0, "normalize_merge_diff_ms": 1, "llm_ms": 9, "entered": True, "skipped": False},
            },
            "llm_calls": [
                {"name": "planner_llm", "node": "phase_policy_planner", "latency_ms": 77, "ok": True},
                {"name": "executor_llm", "node": "executor", "latency_ms": 52, "ok": True},
            ],
        },
        "policy_decision": {"policy_id": "safe_neutral", "why_short": "because"},
        "phase_candidate": {"reasons": ["a", "b"], "alternatives": [{"policy_id": "x", "reason": "r"}]},
        "phase_effective": {"phase": "opening"},
        "allowed_policy_ids": ["safe_neutral"],
        "planner_meta": {},
        "executor_validator_meta": {},
    }

    event = build_trace_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)

    assert event["trace_schema_version"] == "vNext-1"
    assert event["timing"]["turn_total_ms"] == 899
    assert event["timing"]["nodes"]["executor"]["total_ms"] == 15
    assert len(event["timing"]["llm_calls"]) == 2
    assert event["planner_debug_v2"]["input_compact"]["phase_effective"]["phase"] == "opening"


def test_build_trace_event_hides_internals_when_disabled(monkeypatch):
    monkeypatch.setenv("TRACE_LEVEL", "1")
    monkeypatch.setenv("TRACE_INCLUDE_INTERNALS", "0")

    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)

    event = build_trace_event(
        user_id="u",
        session_id="s",
        session=session,
        trace_index=0,
        trace_item={"turn": 1, "policy_decision": {"policy_id": "safe_neutral"}},
    )

    assert event["planner_debug_v2"] == {}
    assert event["executor_debug_v2"] == {}
