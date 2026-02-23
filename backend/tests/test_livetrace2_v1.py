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
from negotiation.nodes.belief_node import belief_updater_node
from negotiation.nodes.policy_progress_node import policy_progress_node
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




def test_livetrace2_same_timestamp_orders_gate_before_synthetic_skipped_llm():
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["gate_events"] = [
        {
            "name": "planner_gate",
            "node": "phase_policy_planner",
            "decision": "skipped",
            "reason": "continue_same_step_without_planner",
            "reason_codes": ["continue_policy_reuse"],
            "start_ts": "2026-01-01T00:00:03+00:00",
            "end_ts": "2026-01-01T00:00:03+00:00",
            "latency_ms": 0,
        }
    ]

    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    names = [node["node_name"] for node in event["nodes"]]
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
    assert advisor[0]["error"] == "disabled_by_config"


def test_world_updater_parallel_advisor_join_error_keeps_realistic_timestamps(monkeypatch):
    monkeypatch.setenv("ADVISOR_ENABLED", "1")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {
            "extractor_llm_latency_ms": 1,
            "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00",
            "extractor_llm_end_ts": "2026-01-01T00:00:00.001+00:00",
        }

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {
            "judge_latency_ms": 1,
            "judge_start_ts": "2026-01-01T00:00:00+00:00",
            "judge_end_ts": "2026-01-01T00:00:00.001+00:00",
            "judge_error_type": "",
        }

    def fake_advisor(**kwargs):
        raise RuntimeError("advisor_boom")

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

    out = world_node.world_updater_node(state)
    out = policy_progress_node(out)
    advisor = next(x for x in out["trace_runtime"]["llm_calls"] if x.get("name") == "advisor_llm")
    assert advisor["status"] == "error"
    assert advisor["start_ts"]
    assert advisor["end_ts"]
    assert "advisor_boom" in advisor["error"]


def test_world_updater_runs_advisor_by_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("ADVISOR_ENABLED", raising=False)
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "0")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {
            "extractor_llm_latency_ms": 1,
            "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00",
            "extractor_llm_end_ts": "2026-01-01T00:00:00.001+00:00",
        }

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {
            "judge_latency_ms": 1,
            "judge_start_ts": "2026-01-01T00:00:00+00:00",
            "judge_end_ts": "2026-01-01T00:00:00.001+00:00",
            "judge_error_type": "",
        }

    def fake_advisor(**kwargs):
        return {}, {
            "advisor_ok": True,
            "advisor_latency_ms": 1,
            "advisor_llm_called": True,
            "advisor_start_ts": "2026-01-01T00:00:00+00:00",
            "advisor_end_ts": "2026-01-01T00:00:00.001+00:00",
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

    out = world_node.world_updater_node(state)
    advisor = next(x for x in out["trace_runtime"]["llm_calls"] if x.get("name") == "advisor_llm")
    assert advisor["status"] == "ok"


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

    # Belief arranca antes de hacer join de judge/advisor.
    out = belief_updater_node(out)
    out = policy_progress_node(out)

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
    out = policy_progress_node(out)
    judge_meta = out["extractor_meta"]["world_judge_meta"]
    assert judge_meta["inputs_world_version"] == "prev_world"
    assert judge_meta["judge_may_be_stale_due_to_world_update"] is True
    assert "world_updated:offers" in judge_meta["staleness_reason_codes"]


def test_belief_can_start_before_judge_finishes(monkeypatch):
    monkeypatch.setenv("ADVISOR_ENABLED", "1")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        start = datetime.now(timezone.utc).isoformat()
        time.sleep(0.04)
        end = datetime.now(timezone.utc).isoformat()
        world = dict(prev_world)
        world["world_buckets"] = {"offers": [{"text": "x"}]}
        return world, {
            "extractor_llm_latency_ms": 40,
            "extractor_llm_start_ts": start,
            "extractor_llm_end_ts": end,
            "updated_buckets": ["offers"],
        }

    def fake_world_judge_llm(**kwargs):
        start = datetime.now(timezone.utc).isoformat()
        time.sleep(0.18)
        end = datetime.now(timezone.utc).isoformat()
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {
            "judge_latency_ms": 180,
            "judge_start_ts": start,
            "judge_end_ts": end,
            "judge_error_type": "",
        }

    def fake_advisor(**kwargs):
        return {}, {"advisor_ok": True, "advisor_latency_ms": 10, "advisor_llm_called": True, "advisor_start_ts": datetime.now(timezone.utc).isoformat(), "advisor_end_ts": datetime.now(timezone.utc).isoformat()}

    def fake_belief(**kwargs):
        return default_belief_state(), {
            "belief_input_prompt_rendered": "belief_prompt",
            "belief_output_text_rendered": "belief_out",
            "belief_input_payload_raw": {"x": 1},
            "belief_output_payload_raw": {"y": 1},
            "belief_latency_ms": 5,
        }

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)
    monkeypatch.setattr(world_node, "build_advisor_recs", fake_advisor)
    monkeypatch.setattr("negotiation.nodes.belief_node.extract_belief_state_llm_v1", fake_belief)

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
    out = belief_updater_node(out)
    out = policy_progress_node(out)
    calls = {x.get("name"): x for x in out["trace_runtime"]["llm_calls"]}
    assert "belief_llm" in calls and "world_judge_llm" in calls
    assert calls["belief_llm"]["start_ts"] < calls["world_judge_llm"]["end_ts"]
    assert out.get("advisor_recs") is not None


def test_world_gate_always_recorded():
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["gate_events"] = [{"name": "world_gate", "node": "world_updater", "decision": "executed", "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00+00:00", "latency_ms": 0}]
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026,1,2,tzinfo=timezone.utc)
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    assert any(node["node_name"] == "world_gate" for node in event["nodes"])


def test_chronological_order_world_belief_planner_executor():
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["llm_calls"] = [
        {"name": "world_extractor_llm", "node": "world_updater", "start_ts": "2026-01-01T00:00:00.010+00:00", "end_ts": "2026-01-01T00:00:00.100+00:00", "latency_ms": 90, "ok": True, "status": "ok"},
        {"name": "belief_llm", "node": "belief_updater", "start_ts": "2026-01-01T00:00:00.120+00:00", "end_ts": "2026-01-01T00:00:00.200+00:00", "latency_ms": 80, "ok": True, "status": "ok"},
        {"name": "planner_llm", "node": "phase_policy_planner", "start_ts": "2026-01-01T00:00:00.260+00:00", "end_ts": "2026-01-01T00:00:00.340+00:00", "latency_ms": 80, "ok": True, "status": "ok"},
        {"name": "executor_llm", "node": "executor", "start_ts": "2026-01-01T00:00:00.350+00:00", "end_ts": "2026-01-01T00:00:00.430+00:00", "latency_ms": 80, "ok": True, "status": "ok"},
    ]
    trace_item["trace_runtime"]["gate_events"] = [
        {"name": "world_gate", "node": "world_updater", "decision": "executed", "start_ts": "2026-01-01T00:00:00.000+00:00", "end_ts": "2026-01-01T00:00:00.005+00:00", "latency_ms": 5},
        {"name": "belief_gate", "node": "belief_updater", "decision": "executed", "start_ts": "2026-01-01T00:00:00.110+00:00", "end_ts": "2026-01-01T00:00:00.111+00:00", "latency_ms": 1},
        {"name": "planner_gate", "node": "phase_policy_planner", "decision": "executed", "start_ts": "2026-01-01T00:00:00.240+00:00", "end_ts": "2026-01-01T00:00:00.241+00:00", "latency_ms": 1},
    ]
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    names = [node["node_name"] for node in event["nodes"]]
    assert names[:7] == ["world_gate", "world_extractor_llm", "belief_gate", "belief_llm", "planner_gate", "planner_llm", "executor_llm"]
    assert [node["sequence_index"] for node in event["nodes"]] == list(range(len(event["nodes"])))


def test_planner_gate_present_when_skipped_and_gate_payload_mapped(monkeypatch):
    monkeypatch.setenv("LIVETRACE2_MODE", "internal")
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["gate_events"] = [
        {
            "name": "planner_gate",
            "node": "phase_policy_planner",
            "decision": "skipped",
            "reason": "judge_skip_planner",
            "reason_codes": ["judge_skip_planner_true"],
            "gate_inputs": {"planner_request": "continue_policy", "judgement_skip_planner": True},
            "start_ts": "2026-01-01T00:00:01+00:00",
            "end_ts": "2026-01-01T00:00:01+00:00",
            "latency_ms": 0,
        }
    ]
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    planner_gate = next(node for node in event["nodes"] if node["node_name"] == "planner_gate")
    assert planner_gate["status"] == "ok"
    assert planner_gate["input_payload_raw"]["planner_request"] == "continue_policy"
    assert planner_gate["output_payload_raw"]["gate_decision"] == "skipped"


def test_planner_gate_skip_adds_synthetic_planner_llm_and_contiguous_sequence(monkeypatch):
    monkeypatch.setenv("LIVETRACE2_MODE", "internal")
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["gate_events"] = [
        {
            "name": "planner_gate",
            "node": "phase_policy_planner",
            "decision": "skipped",
            "reason": "continue_same_step_without_planner",
            "reason_codes": ["continue_policy_reuse"],
            "gate_inputs": {"planner_request": "continue_policy"},
            "start_ts": "2026-01-01T00:00:01+00:00",
            "end_ts": "2026-01-01T00:00:01+00:00",
            "latency_ms": 0,
        }
    ]
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    assert [node["sequence_index"] for node in event["nodes"]] == list(range(len(event["nodes"])))
    planner_llm = next(node for node in event["nodes"] if node["node_name"] == "planner_llm")
    assert planner_llm["status"] == "skipped"
    assert "skipped_by_planner_gate" in planner_llm["output_payload_raw"]["reason_codes"]
