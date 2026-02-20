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
        "gates": {"world_skipped": False, "belief_skipped": False, "planner_skipped": True},
        "extractor_used": True,
        "extractor_reasons": ["llm_extractor_confident"],
        "extractor_world_patch_keys": ["price"],
        "planner_meta": {"reason": "needed_info"},
        "policy_plan_judgement": {"plan_status": "continue_same_step", "degraded": False},
        "world_debug": {"world_judge_meta": {"judge_latency_ms": 123}},
        "belief_debug": {"planner_relevant": {"interaction_health": "stable"}},
        "planner_debug": {"gate_decision": {"gate_path": "skip_continue_policy"}},
        "progress_debug": {"anti_loop_signals": {"continue_loop_detected": False}},
        "belief_update_meta": {"belief_node_entered": True, "belief_updater_invoked": True, "belief_noop_reason": "merge_no_effect"},
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
    assert event["gates_triggered"] == ["planner"]
    choices = {c["gate"]: c for c in event["gate_choices"]}
    assert choices["belief"]["gate_enabled"] is True
    assert choices["belief"]["gate_decision"] == "executed"
    assert choices["planner"]["gate_enabled"] is True
    assert choices["planner"]["gate_decision"] == "skipped"
    assert event["build_git_sha"] == "abc123"
    assert event["belief_node_entered"] is True
    assert event["belief_updater_invoked"] is True
    assert event["belief_noop_reason"] == "merge_no_effect"
    assert event["debug"]["belief"]["belief_node_entered"] is True
    assert event["policy_plan_judgement"]["plan_status"] == "continue_same_step"
    assert event["planner_debug"]["gate_decision"]["gate_path"] == "skip_continue_policy"
    assert event["world_base"]["price"] == 10000
    assert event["world_new"]["price"] == 9500


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


def test_build_trace_event_marks_belief_change_from_meta_backstop_when_diff_empty():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    trace_item = {
        "turn": 5,
        "belief_prev": {"schema_version": "v2", "universal": {}, "negotiation": {}},
        "belief_new": {"schema_version": "v2", "universal": {}, "negotiation": {}},
        "belief_diff": {},
        "belief_update_meta": {
            "belief_merge_changed": True,
            "belief_updated_fields": ["belief_buckets"],
        },
    }

    event = build_trace_event(
        user_id="u1",
        session_id="s1",
        session=session,
        trace_index=0,
        trace_item=trace_item,
    )

    assert event["belief_changed"] is True
    assert "belief_buckets" in event["belief_changed_keys"]
    assert "belief_buckets" in event["belief_diff_keys"]


def test_build_trace_event_detects_belief_buckets_when_present_in_snapshots():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    trace_item = {
        "turn": 6,
        "belief_prev": {
            "schema_version": "v2",
            "universal": {},
            "negotiation": {},
            "belief_buckets": {"hypotheses": ["A"]},
        },
        "belief_new": {
            "schema_version": "v2",
            "universal": {},
            "negotiation": {},
            "belief_buckets": {"hypotheses": ["A", "B"]},
        },
        "belief_diff": {"belief_buckets": {"before": {"hypotheses": ["A"]}, "after": {"hypotheses": ["A", "B"]}}},
    }

    event = build_trace_event(
        user_id="u1",
        session_id="s1",
        session=session,
        trace_index=0,
        trace_item=trace_item,
    )

    assert event["belief_changed"] is True
    assert "belief_buckets" in event["belief_changed_keys"]
    assert "belief_buckets" in event["belief_diff_keys"]



def test_build_trace_event_build_git_sha_source_from_env(monkeypatch):
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("BUILD_ID", raising=False)
    monkeypatch.setenv("BUILD_GIT_SHA", "abc")

    event = build_trace_event(
        user_id="u1",
        session_id="s1",
        session=session,
        trace_index=0,
        trace_item={"turn": 1},
    )

    assert event["build_git_sha"] == "abc"
    assert event["build_git_sha_source"] == "env_BUILD_GIT_SHA"


def test_build_trace_event_build_git_sha_unknown_adds_issue(monkeypatch):
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    monkeypatch.delenv("BUILD_GIT_SHA", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("BUILD_ID", raising=False)

    event = build_trace_event(
        user_id="u1",
        session_id="s1",
        session=session,
        trace_index=0,
        trace_item={"turn": 1},
    )

    assert event["build_git_sha"] == "unknown"
    assert event["build_git_sha_source"] == "unknown"
    assert "build_sha_unknown" in event["exit_issues"]


def test_build_trace_event_gate_semantics_enabled_vs_skipped_are_separate():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    trace_item = {
        "turn": 2,
        "gates": {
            "world_skipped": False,
            "belief_skipped": True,
            "planner_skipped": False,
            "skip_reasons": {"belief": "world_unchanged"},
        },
    }
    event = build_trace_event(user_id="u1", session_id="s1", session=session, trace_index=0, trace_item=trace_item)
    choices = {c["gate"]: c for c in event["gate_choices"]}
    assert choices["belief"]["gate_enabled"] is True
    assert choices["belief"]["gate_decision"] == "skipped"
    assert choices["belief"]["gate_reason"] == "world_unchanged"
    assert choices["world"]["gate_decision"] == "executed"


def test_build_trace_event_marks_world_state_meta_changed_when_turn_advances():
    session = SessionState(user_id="u1", session_id="s1")
    session.last_updated = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    trace_item = {
        "turn": 4,
        "world_prev": {
            "schema_version": "v3",
            "world_buckets": {"offers": []},
            "world_state_meta": {"turn_idx": 3, "updated_fields": []},
        },
        "world_new": {
            "schema_version": "v3",
            "world_buckets": {"offers": [{"text": "Nueva", "confidence": 0.4, "raw_text": "nueva", "source_turn": 4}]},
            "world_state_meta": {"turn_idx": 4, "updated_fields": ["world_buckets.offers"]},
        },
    }

    event = build_trace_event(user_id="u1", session_id="s1", session=session, trace_index=0, trace_item=trace_item)

    assert event["world_base"]["world_state_meta"]["turn_idx"] == 3
    assert event["world_new"]["world_state_meta"]["turn_idx"] == 4
    assert "world_state_meta" in event["world_changed_keys"]
    assert "world_state_meta" not in event["world_unchanged_keys"]
