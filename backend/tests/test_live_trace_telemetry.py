from __future__ import annotations

from datetime import datetime, timezone

from negotiation.telemetry.live_trace import build_trace_event, list_recent_trace_events
from state import SessionState


def test_build_trace_event_shapes_fields():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    trace_item = {
        "turn": 4,
        "user_message": "¿Cuál es el precio final?",
        "assistant_reply": "Podría cerrar en 9.500€ si incluye transferencia.",
        "planner_failed": True,
        "belief_update_failed": False,
        "planner_error": "planner_timeout",
        "policy_decision": {"policy_id": "hold_position"},
        "phase_effective": {"phase": "fase_2_descubrir"},
        "allowed_policy_ids": ["hold_position", "rapport_build"],
        "world_prev": {"price": 10000, "urgency": "media"},
        "world_new": {"price": 9500, "urgency": "media"},
        "world_diff": {"price": {"before": 10000, "after": 9500}},
        "belief_prev": {"stance": "neutral", "trust": "media"},
        "belief_new": {"stance": "cooperative", "trust": "media"},
        "belief_diff": {"stance": {"before": "neutral", "after": "cooperative"}},
        "gates": {"gate_world": True, "gate_belief": False},
        "extractor_used": True,
        "extractor_reasons": ["llm_extractor_confident"],
        "extractor_world_patch_keys": ["price"],
        "planner_meta": {"reason": "needed_info"},
        "belief_update_meta": {"belief_node_entered": True, "belief_updater_invoked": True},
        "build_git_sha": "abc123",
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
    assert event["final_reply"].startswith("Podría cerrar")
    assert event["input_message"].startswith("¿Cuál")
    assert event["planner_failed"] is True
    assert event["policy"] == "hold_position"
    assert event["phase"] == "fase_2_descubrir"
    assert event["world_diff_keys"] == ["price"]
    assert event["belief_diff_keys"] == ["stance"]
    assert event["world_changed_keys"] == ["price"]
    assert event["world_unchanged_keys"] == ["urgency"]
    assert event["belief_changed_keys"] == ["stance"]
    assert event["belief_unchanged_keys"] == ["trust"]
    assert event["gates_triggered"] == ["gate_world"]
    assert event["gate_choices"][0]["gate"] == "gate_belief"
    assert event["gate_choices"][1]["selected"] == "enabled"
    assert event["build_git_sha"] == "abc123"
    assert event["debug"]["belief"]["belief_node_entered"] is True


def test_list_recent_trace_events_aggregates_sessions():
    old_session = SessionState(user_id="u-old", session_id="s-old")
    old_session.last_updated = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    old_session.debug_trace = [{"turn": 1, "policy_decision": {"policy_id": "a"}}]

    new_session = SessionState(user_id="u-new", session_id="s-new")
    new_session.last_updated = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    new_session.debug_trace = [
        {"turn": 1, "policy_decision": {"policy_id": "b"}},
        {"turn": 2, "policy_decision": {"policy_id": "c"}, "assistant_reply": "respuesta"},
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
    assert events[-1]["final_reply"] == "respuesta"
