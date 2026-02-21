from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from negotiation.schemas import default_belief_state, default_progress_state, default_world_state
from negotiation.telemetry.live_trace2 import build_livetrace2_event
from negotiation.telemetry.trace_runtime import init_trace_runtime
from negotiation.nodes import world_node
from state import SessionState


def _base_trace_item() -> dict:
    return {
        "turn": 1,
        "user_message": "hola",
        "assistant_reply": "ok",
        "trace_runtime": init_trace_runtime(),
    }


def test_livetrace2_event_validates_against_schema():
    schema = json.loads(Path("docs/livetrace2_event.schema.json").read_text())
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["llm_calls"] = [
        {
            "name": "world_extractor_llm",
            "node": "world_updater",
            "start_ts": "2026-01-01T00:00:00+00:00",
            "end_ts": "2026-01-01T00:00:00.100000+00:00",
            "latency_ms": 100,
            "ok": True,
            "status": "ok",
            "input_prompt_rendered": "prompt",
            "output_text_rendered": "raw",
        }
    ]
    trace_item["trace_runtime"]["gate_events"] = [
        {
            "name": "world_gate",
            "node": "world_updater",
            "decision": "executed",
            "reason": "always_refresh_user_turn",
            "reason_codes": ["always_refresh_user_turn"],
            "gate_inputs": {"user_message_empty": False},
            "gate_rule_id": "gate_world",
            "gate_version": "v1",
            "start_ts": "2026-01-01T00:00:00+00:00",
            "end_ts": "2026-01-01T00:00:00.001000+00:00",
            "latency_ms": 1,
        }
    ]
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    assert "world_parallelism" in event
    jsonschema.validate(event, schema)


def test_livetrace2_orders_gates_before_belief_and_planner_llm():
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["llm_calls"] = [
        {
            "name": "belief_llm",
            "node": "belief_updater",
            "start_ts": "2026-01-01T00:00:02+00:00",
            "end_ts": "2026-01-01T00:00:02.1+00:00",
            "latency_ms": 100,
            "ok": True,
            "status": "ok",
        },
        {
            "name": "planner_llm",
            "node": "phase_policy_planner",
            "start_ts": "2026-01-01T00:00:03+00:00",
            "end_ts": "2026-01-01T00:00:03.1+00:00",
            "latency_ms": 100,
            "ok": True,
            "status": "ok",
        },
    ]
    trace_item["trace_runtime"]["gate_events"] = [
        {
            "name": "belief_gate",
            "node": "belief_updater",
            "decision": "executed",
            "start_ts": "2026-01-01T00:00:01+00:00",
            "end_ts": "2026-01-01T00:00:01+00:00",
            "latency_ms": 0,
        },
        {
            "name": "planner_gate",
            "node": "phase_policy_planner",
            "decision": "executed",
            "start_ts": "2026-01-01T00:00:02.500000+00:00",
            "end_ts": "2026-01-01T00:00:02.500000+00:00",
            "latency_ms": 0,
        },
    ]
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    names = [node["node_name"] for node in event["nodes"]]
    assert names.index("belief_gate") < names.index("belief_llm")
    assert names.index("planner_gate") < names.index("planner_llm")


def test_livetrace2_public_mode_redacts_payload(monkeypatch):
    monkeypatch.setenv("LIVETRACE2_MODE", "public")
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["llm_calls"] = [
        {
            "name": "executor_llm",
            "node": "executor",
            "start_ts": "2026-01-01T00:00:00+00:00",
            "end_ts": "2026-01-01T00:00:00.010000+00:00",
            "latency_ms": 10,
            "ok": True,
            "status": "ok",
            "input_payload_raw": {"user_message": "secreto"},
            "output_payload_raw": {"answer": "dato"},
        }
    ]
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    node = event["nodes"][0]
    assert node["redaction_applied"] is True
    assert node["input_payload_raw"]["_redacted"] is True


def test_world_updater_records_advisor_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("ADVISOR_ENABLED", "0")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "0")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {
            "extractor_llm_latency_ms": 1,
            "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00",
            "extractor_llm_end_ts": "2026-01-01T00:00:00.001+00:00",
            "extractor_input_prompt_rendered": "p",
            "extractor_output_text_rendered": "o",
        }

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {
            "judge_latency_ms": 1,
            "judge_start_ts": "2026-01-01T00:00:00+00:00",
            "judge_end_ts": "2026-01-01T00:00:00.001+00:00",
            "judge_error_type": "",
        }

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)

    state = {
        "deps": None,
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": default_progress_state(),
        "user_message": "hola",
        "turn_count": 1,
        "input_modality": "text",
        "recent_history_text": "",
        "short_memory": "",
        "long_memory": "",
        "objective": "",
        "trace_runtime": init_trace_runtime(),
    }
    out = world_node.world_updater_node(state)
    advisor = [x for x in out["trace_runtime"]["llm_calls"] if x.get("name") == "advisor_llm"]
    assert advisor
    assert advisor[0]["status"] == "skipped"


def test_world_parallelism_overlaps_tasks(monkeypatch):
    monkeypatch.setenv("ADVISOR_ENABLED", "1")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        start = datetime.now(timezone.utc).isoformat()
        time.sleep(0.12)
        end = datetime.now(timezone.utc).isoformat()
        return prev_world, {
            "extractor_llm_latency_ms": 120,
            "extractor_llm_start_ts": start,
            "extractor_llm_end_ts": end,
            "extractor_input_prompt_rendered": "extractor prompt",
            "extractor_output_text_rendered": "extractor output",
        }

    def fake_world_judge_llm(**kwargs):
        start = datetime.now(timezone.utc).isoformat()
        time.sleep(0.12)
        end = datetime.now(timezone.utc).isoformat()
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {
            "judge_latency_ms": 120,
            "judge_start_ts": start,
            "judge_end_ts": end,
            "judge_error_type": "",
        }

    def fake_advisor(**kwargs):
        start = datetime.now(timezone.utc).isoformat()
        time.sleep(0.12)
        end = datetime.now(timezone.utc).isoformat()
        return {}, {
            "advisor_ok": True,
            "advisor_latency_ms": 120,
            "advisor_llm_called": True,
            "advisor_start_ts": start,
            "advisor_end_ts": end,
        }

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)
    monkeypatch.setattr(world_node, "build_advisor_recs", fake_advisor)

    state = {
        "deps": None,
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": default_progress_state(),
        "user_message": "hola",
        "turn_count": 1,
        "input_modality": "text",
        "recent_history_text": "",
        "short_memory": "",
        "long_memory": "",
        "objective": "",
        "trace_runtime": init_trace_runtime(),
    }

    t0 = time.perf_counter()
    out = world_node.world_updater_node(state)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.30

    calls = {x.get("name"): x for x in out["trace_runtime"]["llm_calls"]}
    assert "world_extractor_llm" in calls
    assert "world_judge_llm" in calls
    assert "advisor_llm" in calls
    assert calls["world_extractor_llm"]["start_ts"]
    assert calls["world_judge_llm"]["start_ts"]
    assert calls["advisor_llm"]["start_ts"]


def test_world_parallelism_metrics_with_advisor_disabled(monkeypatch):
    monkeypatch.setenv("ADVISOR_ENABLED", "0")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {"extractor_llm_latency_ms": 90, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.090000+00:00", "updated_buckets": ["offers"]}

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 30, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.030000+00:00", "judge_error_type": ""}

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)

    state = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out = world_node.world_updater_node(state)
    wp = out["world_parallelism"]
    assert wp["enabled"] is True
    assert wp["sum_ms"] >= wp["critical_path_ms"] >= 0
    assert wp["overlap_ms"] >= 0
    assert wp["saved_ms_estimate"] == wp["overlap_ms"]


def test_staleness_flag_when_world_updates_material_bucket(monkeypatch):
    monkeypatch.setenv("ADVISOR_ENABLED", "0")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {"extractor_llm_latency_ms": 10, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.010000+00:00", "updated_buckets": ["offers"]}

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 10, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.010000+00:00", "judge_error_type": ""}

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)

    state = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out = world_node.world_updater_node(state)
    judge_meta = out["extractor_meta"]["world_judge_meta"]
    assert judge_meta["inputs_world_version"] == "prev_world"
    assert judge_meta["judge_may_be_stale_due_to_world_update"] is True
    assert "world_updated:offers" in judge_meta["staleness_reason_codes"]


def test_world_gate_always_recorded():
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["gate_events"] = [{"name": "world_gate", "node": "world_updater", "decision": "executed", "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00+00:00", "latency_ms": 0}]
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026,1,2,tzinfo=timezone.utc)
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    assert any(node["node_name"] == "world_gate" for node in event["nodes"])
