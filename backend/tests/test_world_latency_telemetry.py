from __future__ import annotations

from negotiation.nodes.world_node import world_updater_node
from negotiation.schemas import default_progress_state, default_world_state
from negotiation.telemetry.live_trace import build_trace_event
from negotiation.telemetry.llm_usage import extract_llm_usage
from negotiation.telemetry.trace_runtime import init_trace_runtime, record_llm_call
from state import SessionState


class _Raw:
    response_metadata = {
        "model_name": "gpt-test",
        "token_usage": {"prompt_tokens": 11, "completion_tokens": 7},
        "queue_ms": 13,
        "ttfb_ms": 21,
    }
    usage_metadata = {"input_tokens": 11, "output_tokens": 7}


def test_extract_llm_usage_reads_model_and_tokens():
    usage = extract_llm_usage(_Raw())
    assert usage["model"] == "gpt-test"
    assert usage["tokens_in"] == 11
    assert usage["tokens_out"] == 7
    assert usage["queue_ms"] == 13
    assert usage["ttfb_ms"] == 21


def test_record_llm_call_start_end_are_coherent():
    state = {"trace_runtime": init_trace_runtime()}
    started = 1.0
    record_llm_call(state, name="x", node="world_updater", started=started, ok=True)
    call = state["trace_runtime"]["llm_calls"][0]
    assert call["start_ts"]
    assert call["end_ts"]
    assert call["latency_ms"] >= 1


def test_world_updater_records_extractor_llm_and_fastpath_no_change(monkeypatch):
    monkeypatch.setenv("WORLD_PARALLELISM_ENABLED", "0")
    world = default_world_state()

    def fake_gate_world(**_kwargs):
        return False, "", {}

    def fake_update_world_state(prev_world, *_args, **_kwargs):
        return prev_world, {
            "extractor_used": True,
            "extractor_failed": False,
            "extractor_llm_latency_ms": 42,
            "extractor_llm_start_ts": "2026-01-01T00:00:00+00:00",
            "extractor_llm_end_ts": "2026-01-01T00:00:01+00:00",
            "extractor_llm_model": "gpt-world",
            "extractor_llm_tokens_in": 12,
            "extractor_llm_tokens_out": 8,
            "timers": {"world_merge_ms": 1},
            "diff_paths": [],
            "prev_world_bytes": 10,
            "world_diff_bytes": 2,
        }

    def fake_world_judge_llm(**_kwargs):
        return {"plan_status": "continue_same_step", "missing_signals": [], "safety_flags": []}, {
            "judge_latency_ms": 3,
            "judge_error_type": "",
            "judge_retry_count": 0,
            "judge_start_ts": "2026-01-01T00:00:02+00:00",
            "judge_end_ts": "2026-01-01T00:00:03+00:00",
            "judge_model": "gpt-judge",
            "judge_tokens_in": 5,
            "judge_tokens_out": 4,
        }

    monkeypatch.setattr("negotiation.nodes.world_node.gate_world", fake_gate_world)
    monkeypatch.setattr("negotiation.nodes.world_node.update_world_state", fake_update_world_state)
    monkeypatch.setattr("negotiation.nodes.world_node.world_judge_llm", fake_world_judge_llm)

    state = {
        "deps": object(),
        "world_state": world,
        "belief_state": {},
        "progress_state": default_progress_state(),
        "user_message": "hola",
        "turn_count": 1,
        "input_modality": "text",
        "recent_history": [],
        "recent_history_text": "",
        "objective": "",
        "last_assistant_message": "",
        "short_memory": "",
        "long_memory": "",
        "trace_runtime": init_trace_runtime(),
    }

    out = world_updater_node(state)
    llm_names = [item.get("name") for item in out["trace_runtime"]["llm_calls"]]
    assert "world_extractor_llm" in llm_names
    assert "world_judge_llm" in llm_names
    assert out["world_diff"] == {}
    assert out["extractor_meta"]["diff_paths"] == []


def test_live_trace_exposes_world_timers():
    session = SessionState(user_id="u", session_id="s")
    event = build_trace_event(
        user_id="u",
        session_id="s",
        session=session,
        trace_index=0,
        trace_item={
            "turn": 1,
            "assistant_reply": "ok",
            "user_message": "hola",
            "world_prev": {},
            "world_new": {},
            "world_diff": {},
            "belief_prev": {},
            "belief_new": {},
            "belief_diff": {},
            "policy_decision": {"policy_id": "safe_neutral"},
            "phase_effective": {"phase": "climate"},
            "planner_meta": {},
            "gates": {},
            "world_debug": {"timers": {"world_merge_ms": 5}},
            "trace_runtime": init_trace_runtime(),
        },
    )
    assert event["world_timers"]["world_merge_ms"] == 5
