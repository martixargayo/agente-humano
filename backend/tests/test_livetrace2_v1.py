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
from negotiation.nodes.planner_node import phase_policy_planner_node
from negotiation import advisor as advisor_module
from negotiation.negotiation_graph import NegotiationTurn
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


def test_livetrace2_header_includes_build_and_env_snapshot(monkeypatch):
    monkeypatch.setenv("BUILD_GIT_SHA", "abc123")
    monkeypatch.setenv("BUILD_VERSION", "vtest")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")
    monkeypatch.setenv("ADVISOR_ENABLED", "0")
    monkeypatch.setenv("LIVETRACE2_MODE", "internal")
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=3, trace_item=_base_trace_item())
    header = event["header"]
    assert header["build_git_sha"] == "abc123"
    assert header["build_version"] == "vtest"
    assert header["server_instance_id"]
    assert header["env_snapshot"] == {
        "WORLD_PARALLELISM_ENABLED": "1",
        "ADVISOR_ENABLED": "0",
        "LIVETRACE2_MODE": "internal",
    }


def test_livetrace2_header_includes_event_identity():
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["turn"] = 9
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=7, trace_item=trace_item)
    assert event["header"]["event_identity"] == {"session_id": "s", "trace_index": 7, "turn": 9}
    assert event["event_identity"] == {"session_id": "s", "trace_index": 7, "turn": 9}


def _assert_parallelism_chain_or_raise(*, state_after_world: dict, trace_item: dict, event: dict) -> None:
    if not isinstance(state_after_world.get("world_parallelism"), dict) or not state_after_world.get("world_parallelism"):
        raise AssertionError("missing_at_state:world_updater")
    if not isinstance(trace_item.get("world_parallelism"), dict) or not trace_item.get("world_parallelism"):
        raise AssertionError("missing_at_trace_item:debug_trace")
    if not isinstance(event.get("world_parallelism"), dict) or not event.get("world_parallelism"):
        raise AssertionError("missing_at_event:build_livetrace2_event")


def test_parallelism_propagates_to_event_header_and_nodes(monkeypatch):
    monkeypatch.setenv("ADVISOR_ENABLED", "1")
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {"extractor_llm_latency_ms": 120, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.120000+00:00"}

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 120, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.120000+00:00", "judge_error_type": ""}

    def fake_advisor(**kwargs):
        return {"recs": []}, {"advisor_ok": True, "advisor_latency_ms": 70, "advisor_llm_called": True, "advisor_start_ts": "2026-01-01T00:00:00+00:00", "advisor_end_ts": "2026-01-01T00:00:00.070000+00:00", "advisor_output_payload_raw": {"recs": []}}

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)
    monkeypatch.setattr(world_node, "build_advisor_recs", fake_advisor)

    state = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out = world_node.world_updater_node(state)
    out = policy_progress_node(out)
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = {"turn": 1, "trace_runtime": out["trace_runtime"], "world_parallelism": out.get("world_parallelism", {})}
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    _assert_parallelism_chain_or_raise(state_after_world=out, trace_item=trace_item, event=event)

    wp = event["world_parallelism"]
    assert wp["enabled"] is True
    assert wp["sum_ms"] >= wp["critical_path_ms"] >= 0
    assert wp["overlap_ms"] >= 0
    assert wp["saved_ms_estimate"] >= 0

    calls = {x.get("node_name"): x for x in event["nodes"]}
    assert calls["world_extractor_llm"]["started_at"] <= calls["world_judge_llm"]["ended_at"]


def test_parallelism_missing_is_detected_with_precise_breakpoint(monkeypatch):
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")
    monkeypatch.setenv("ADVISOR_ENABLED", "0")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {"extractor_llm_latency_ms": 10, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.010000+00:00"}

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 10, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.010000+00:00", "judge_error_type": ""}

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)

    state = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out = policy_progress_node(world_node.world_updater_node(state))
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = {"turn": 1, "trace_runtime": out["trace_runtime"], "world_parallelism": {}}
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)

    try:
        _assert_parallelism_chain_or_raise(state_after_world=out, trace_item=trace_item, event=event)
        assert False, "expected assertion"
    except AssertionError as exc:
        assert "missing_at_trace_item:debug_trace" in str(exc)


def test_advisor_status_ok_error_skipped_are_explicit_and_informative(monkeypatch):
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "0")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {"extractor_llm_latency_ms": 5, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.005000+00:00"}

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 5, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.005000+00:00", "judge_error_type": ""}

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)

    # ok
    monkeypatch.setenv("ADVISOR_ENABLED", "1")
    monkeypatch.setattr(world_node, "build_advisor_recs", lambda **kwargs: ({"ok": True}, {"advisor_ok": True, "advisor_latency_ms": 6, "advisor_llm_called": True, "advisor_start_ts": "2026-01-01T00:00:00+00:00", "advisor_end_ts": "2026-01-01T00:00:00.006000+00:00", "advisor_input_prompt_rendered": "p", "advisor_output_text_rendered": "o", "advisor_output_payload_raw": {"ok": True}}))
    st = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out_ok = world_node.world_updater_node(st)
    advisor_ok = next(x for x in out_ok["trace_runtime"]["llm_calls"] if x.get("name") == "advisor_llm")
    assert advisor_ok["status"] == "ok"
    assert advisor_ok["output_payload_raw"] is not None

    # error
    monkeypatch.setattr(world_node, "build_advisor_recs", lambda **kwargs: ({}, {"advisor_ok": False, "advisor_latency_ms": 3, "advisor_error": "boom", "advisor_llm_called": False, "advisor_start_ts": "2026-01-01T00:00:00+00:00", "advisor_end_ts": "2026-01-01T00:00:00.003000+00:00"}))
    st2 = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out_err = world_node.world_updater_node(st2)
    advisor_err = next(x for x in out_err["trace_runtime"]["llm_calls"] if x.get("name") == "advisor_llm")
    assert advisor_err["status"] == "error"
    assert advisor_err["error"]

    # skipped disabled
    monkeypatch.setenv("ADVISOR_ENABLED", "0")
    st3 = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out_skip = world_node.world_updater_node(st3)
    advisor_skip = next(x for x in out_skip["trace_runtime"]["llm_calls"] if x.get("name") == "advisor_llm")
    assert advisor_skip["status"] == "skipped"
    assert advisor_skip["error"] == "disabled_by_config"


def test_env_snapshot_propagation(monkeypatch):
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")
    monkeypatch.setenv("ADVISOR_ENABLED", "0")
    monkeypatch.setenv("LIVETRACE2_MODE", "internal")
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=_base_trace_item())
    got = event["header"]["env_snapshot"]
    assert got == {
        "WORLD_PARALLELISM_ENABLED": "1",
        "ADVISOR_ENABLED": "0",
        "LIVETRACE2_MODE": "internal",
    }, f"env_snapshot mismatch; got={got}"


def _assert_markers_chain_or_raise(*, state_after_policy: dict, trace_item: dict, event: dict) -> None:
    required = {
        "world_updater_entered",
        "world_parallel_scheduled_at",
        "pending_payload_stored",
        "flush_started_at",
        "flush_completed_at",
        "world_parallelism_written_to_state",
        "policy_progress_entered_after_flush",
    }

    def names(items):
        return {str(x.get("marker", "")) for x in (items or []) if isinstance(x, dict)}

    state_names = names(state_after_policy.get("trace_debug_markers"))
    if not required.issubset(state_names):
        raise AssertionError(f"missing_at_state:{sorted(required-state_names)}")
    trace_names = names(trace_item.get("trace_debug_markers"))
    if not required.issubset(trace_names):
        raise AssertionError(f"missing_at_debug_trace:{sorted(required-trace_names)}")
    event_names = names(event.get("trace_debug_markers"))
    if not required.issubset(event_names):
        raise AssertionError(f"missing_at_event:{sorted(required-event_names)}")


def test_trace_debug_markers_propagate(monkeypatch):
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")
    monkeypatch.setenv("ADVISOR_ENABLED", "1")

    def fake_update_world_state(prev_world, user_message, **kwargs):
        return prev_world, {"extractor_llm_latency_ms": 10, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.010000+00:00"}

    def fake_world_judge_llm(**kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 20, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.020000+00:00", "judge_error_type": ""}

    def fake_advisor(**kwargs):
        return {}, {"advisor_ok": True, "advisor_latency_ms": 15, "advisor_llm_called": True, "advisor_start_ts": "2026-01-01T00:00:00+00:00", "advisor_end_ts": "2026-01-01T00:00:00.015000+00:00", "advisor_output_payload_raw": {"diagnosis": []}}

    monkeypatch.setattr(world_node, "update_world_state", fake_update_world_state)
    monkeypatch.setattr(world_node, "world_judge_llm", fake_world_judge_llm)
    monkeypatch.setattr(world_node, "build_advisor_recs", fake_advisor)

    state = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out = policy_progress_node(world_node.world_updater_node(state))
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = {"turn": 1, "trace_runtime": out["trace_runtime"], "world_parallelism": out.get("world_parallelism", {}), "trace_debug_markers": out.get("trace_debug_markers", [])}
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    _assert_markers_chain_or_raise(state_after_policy=out, trace_item=trace_item, event=event)


def test_world_parallelism_written_when_expected(monkeypatch):
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "1")
    monkeypatch.setenv("ADVISOR_ENABLED", "1")

    monkeypatch.setattr(world_node, "update_world_state", lambda prev_world, user_message, **kwargs: (prev_world, {"extractor_llm_latency_ms": 8, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.008000+00:00"}))
    monkeypatch.setattr(world_node, "world_judge_llm", lambda **kwargs: ({"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 12, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.012000+00:00", "judge_error_type": ""}))
    monkeypatch.setattr(world_node, "build_advisor_recs", lambda **kwargs: ({}, {"advisor_ok": True, "advisor_latency_ms": 7, "advisor_llm_called": True, "advisor_start_ts": "2026-01-01T00:00:00+00:00", "advisor_end_ts": "2026-01-01T00:00:00.007000+00:00", "advisor_output_payload_raw": {"diagnosis": []}}))

    state = {"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()}
    out = policy_progress_node(world_node.world_updater_node(state))
    assert isinstance(out.get("world_parallelism"), dict) and out["world_parallelism"]

    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item={"turn": 1, "trace_runtime": out["trace_runtime"], "world_parallelism": out.get("world_parallelism", {})})
    assert isinstance(event.get("world_parallelism"), dict) and event["world_parallelism"]


def test_advisor_error_contains_diagnostics(monkeypatch):
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "0")
    monkeypatch.setenv("ADVISOR_ENABLED", "1")

    monkeypatch.setattr(world_node, "update_world_state", lambda prev_world, user_message, **kwargs: (prev_world, {"extractor_llm_latency_ms": 3, "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00", "extractor_llm_end_ts": "2026-01-01T00:00:00.003000+00:00"}))
    monkeypatch.setattr(world_node, "world_judge_llm", lambda **kwargs: ({"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {"judge_latency_ms": 4, "judge_start_ts": "2026-01-01T00:00:00+00:00", "judge_end_ts": "2026-01-01T00:00:00.004000+00:00", "judge_error_type": ""}))
    monkeypatch.setattr(world_node, "build_advisor_recs", lambda **kwargs: ({}, {"advisor_ok": False, "advisor_llm_called": False, "advisor_error": "KeyError: diagnosis", "advisor_error_type": "KeyError", "advisor_error_stage": "prompt_format", "advisor_start_ts": "2026-01-01T00:00:00+00:00", "advisor_end_ts": "2026-01-01T00:00:00.001000+00:00", "advisor_output_payload_raw": {"error_type": "KeyError", "error_message": "KeyError: diagnosis", "stage": "prompt_format"}}))

    out = world_node.world_updater_node({"deps": None, "world_state": default_world_state(), "belief_state": default_belief_state(), "progress_state": default_progress_state(), "user_message": "hola", "turn_count": 1, "input_modality": "text", "recent_history_text": "", "short_memory": "", "long_memory": "", "objective": "", "trace_runtime": init_trace_runtime()})
    advisor = next(x for x in out["trace_runtime"]["llm_calls"] if x.get("name") == "advisor_llm")
    assert advisor["status"] == "error"
    assert "KeyError" in advisor["error"] and "diagnosis" in advisor["error"]
    assert advisor["output_payload_raw"]["error_type"] == "KeyError"
    assert advisor["output_payload_raw"]["stage"] == "prompt_format"


def test_planner_gate_emission_contract():
    state = {
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": default_progress_state(),
        "objective": "x",
        "trace_runtime": init_trace_runtime(),
        "policy_plan_judgement": {"skip_planner": True},
    }
    out = phase_policy_planner_node(state)
    planner_gates = [x for x in out["trace_runtime"]["gate_events"] if x.get("name") == "planner_gate"]
    assert len(planner_gates) == 1, f"expected single planner_gate, got={planner_gates}"


def test_state_schema_keeps_world_parallelism_and_markers():
    fields = getattr(NegotiationTurn, "__annotations__", {})
    assert "world_parallelism" in fields
    assert "trace_debug_markers" in fields
    assert "_pending_world_parallel" in fields
    assert "world_parallel_pending_key" in fields


def test_debug_trace_includes_world_parallelism_and_markers():
    trace_item = _base_trace_item()
    trace_item["world_parallelism"] = {"enabled": True, "mode": "thread_pool", "sum_ms": 11}
    trace_item["trace_debug_markers"] = [{"marker": "world_parallel_scheduled_at"}]
    trace_item["trace_state_probe"] = {"has_world_parallelism": True, "trace_debug_markers_count": 1}
    assert trace_item["world_parallelism"]["enabled"] is True
    assert trace_item["trace_debug_markers"][0]["marker"] == "world_parallel_scheduled_at"


def test_event_header_reason_code(monkeypatch):
    monkeypatch.setenv("LIVETRACE2_MODE", "internal")
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)

    trace_missing = _base_trace_item()
    event_missing = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_missing)
    assert event_missing["header"]["world_parallelism_reason_code"] in {"missing_in_trace_item", "computed_from_llm_calls_fallback"}

    trace_with_calls = _base_trace_item()
    trace_with_calls["trace_runtime"]["llm_calls"] = [
        {"name": "world_extractor_llm", "status": "ok", "latency_ms": 7, "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00.007000+00:00"},
        {"name": "world_judge_llm", "status": "ok", "latency_ms": 12, "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00.012000+00:00"},
        {"name": "advisor_llm", "status": "ok", "latency_ms": 10, "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00.010000+00:00"},
    ]
    event_fallback = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=1, trace_item=trace_with_calls)
    assert event_fallback["header"]["world_parallelism_reason_code"] == "computed_from_llm_calls_fallback"


def test_event_parallelism_computed_when_missing():
    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = _base_trace_item()
    trace_item["trace_runtime"]["llm_calls"] = [
        {"name": "world_extractor_llm", "status": "ok", "latency_ms": 8, "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00.008000+00:00"},
        {"name": "world_judge_llm", "status": "ok", "latency_ms": 20, "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00.020000+00:00"},
        {"name": "advisor_llm", "status": "ok", "latency_ms": 6, "start_ts": "2026-01-01T00:00:00+00:00", "end_ts": "2026-01-01T00:00:00.006000+00:00"},
    ]
    event = build_livetrace2_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)
    assert event["world_parallelism"]["enabled"] is True
    assert event["world_parallelism"]["mode"] == "computed_from_llm_calls"
    assert event["world_parallelism"]["overlap_ms"] >= 0


class _FakeRaw:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)

    def invoke(self, _messages):
        if not self.outputs:
            return _FakeRaw("{}")
        return _FakeRaw(self.outputs.pop(0))


def test_advisor_invalid_json_produces_diagnostics(monkeypatch):
    monkeypatch.setattr(advisor_module, "get_planner_llm", lambda: _FakeLLM(["{diagnosis: [oops], }"]))
    recs, meta = advisor_module.build_advisor_recs(
        objective="o", recent_history="h", memory_short="", memory_long="", active_plan={}, progress_state={}, world_state={}, belief_state={}
    )
    assert recs == advisor_module._normalize_advisor({})
    assert meta["advisor_error_stage"] in {"repair_retry", "json_parse"}
    payload = meta.get("advisor_output_payload_raw") or {}
    assert payload.get("error_type")
    assert payload.get("stage")
    assert payload.get("advisor_initial_output_text_sha256")
    assert isinstance(payload.get("advisor_initial_output_text_snippet_head"), str)
    assert isinstance(payload.get("advisor_initial_output_text_snippet_tail"), str)


def test_advisor_repair_parse_success(monkeypatch):
    monkeypatch.setattr(advisor_module, "get_planner_llm", lambda: _FakeLLM(["{'diagnosis':['ok'], 'do_not_do': [],}"]))
    recs, meta = advisor_module.build_advisor_recs(
        objective="o", recent_history="h", memory_short="", memory_long="", active_plan={}, progress_state={}, world_state={}, belief_state={}
    )
    assert meta["advisor_ok"] is True
    assert recs["diagnosis"] == ["ok"]
    assert "single_quotes_fixed" in str(meta.get("advisor_parse_strategy", ""))




def test_advisor_repair_invalid_json_includes_repair_diagnostics(monkeypatch):
    fake = _FakeLLM(["{bad json}", "Claro, aquí tienes: nope"])
    monkeypatch.setattr(advisor_module, "get_planner_llm", lambda: fake)
    recs, meta = advisor_module.build_advisor_recs(
        objective="o", recent_history="h", memory_short="", memory_long="", active_plan={}, progress_state={}, world_state={}, belief_state={}
    )
    assert recs == advisor_module._normalize_advisor({})
    assert meta["advisor_error_stage"] == "repair_retry"
    payload = meta.get("advisor_output_payload_raw") or {}
    assert payload.get("advisor_repair_output_text_sha256")
    assert payload.get("advisor_repair_output_text_len", 0) > 0
    assert payload.get("advisor_repair_output_first_char_codepoint") == ord("C")


def test_advisor_structured_output_path(monkeypatch):
    class _Structured:
        def invoke(self, _messages):
            return advisor_module.AdvisorStructuredPayload(diagnosis=["structured"])

    class _StructuredLLM:
        def with_structured_output(self, _schema):
            return _Structured()

    monkeypatch.setattr(advisor_module, "get_planner_llm", lambda: _StructuredLLM())
    recs, meta = advisor_module.build_advisor_recs(
        objective="o", recent_history="h", memory_short="", memory_long="", active_plan={}, progress_state={}, world_state={}, belief_state={}
    )
    assert meta["advisor_ok"] is True
    assert meta.get("advisor_parse_strategy") == "structured_output"
    assert recs["diagnosis"] == ["structured"]

def test_advisor_retry_repair_success(monkeypatch):
    fake = _FakeLLM(["not-json", '{"diagnosis":["fixed"]}'])
    monkeypatch.setattr(advisor_module, "get_planner_llm", lambda: fake)
    recs, meta = advisor_module.build_advisor_recs(
        objective="o", recent_history="h", memory_short="", memory_long="", active_plan={}, progress_state={}, world_state={}, belief_state={}
    )
    assert meta["advisor_ok"] is True
    assert recs["diagnosis"] == ["fixed"]
    assert str(meta.get("advisor_parse_strategy", "")).startswith("repair_retry:")
