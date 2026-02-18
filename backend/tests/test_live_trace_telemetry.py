from __future__ import annotations

from datetime import datetime, timezone

from negotiation.telemetry.live_trace import build_trace_event, list_recent_trace_events
from state import SessionState


def test_build_trace_event_shapes_fields():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    trace_item = {
        "turn": 4,
        "planner_failed": True,
        "belief_update_failed": False,
        "policy_decision": {"policy_id": "hold_position"},
        "phase_effective": {"phase": "fase_2_descubrir"},
        "world_diff": {"price": {"before": 1, "after": 2}},
        "belief_diff": {"stance": {"before": {}, "after": {}}},
        "gates": {"gate_world": True, "gate_belief": False},
        "extractor_used": True,
        "planner_meta": {"reason": "needed_info"},
    }

    event = build_trace_event(
        user_id="u1",
        session_id="s1",
        session=session,
        trace_index=0,
        trace_item=trace_item,
    )

    assert event["session_id"] == "s1"
    assert event["turn"] == 4
    assert event["planner_failed"] is True
    assert event["policy"] == "hold_position"
    assert event["phase"] == "fase_2_descubrir"
    assert event["world_diff_keys"] == ["price"]
    assert event["belief_diff_keys"] == ["stance"]
    assert event["gates_triggered"] == ["gate_world"]


def test_list_recent_trace_events_aggregates_sessions():
    old_session = SessionState(user_id="u-old", session_id="s-old")
    old_session.last_updated = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    old_session.debug_trace = [{"turn": 1, "policy_decision": {"policy_id": "a"}}]

    new_session = SessionState(user_id="u-new", session_id="s-new")
    new_session.last_updated = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    new_session.debug_trace = [
        {"turn": 1, "policy_decision": {"policy_id": "b"}},
        {"turn": 2, "policy_decision": {"policy_id": "c"}},
    ]

    events = list_recent_trace_events(
        {
            ("u-old", "s-old"): old_session,
            ("u-new", "s-new"): new_session,
        },
        max_sessions=2,
        max_traces_per_session=10,
    )

    assert len(events) == 3
    assert events[-1]["session_id"] == "s-new"
    assert events[-1]["turn"] == 2
