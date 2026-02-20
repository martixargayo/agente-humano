from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from negotiation.negotiation_graph import run_negotiation_agent
from negotiation.telemetry.live_trace import build_trace_event
from negotiation.schemas import default_belief_state, default_policy_decision, default_progress_state, default_world_state
from state import SessionState


def _fake_execute(messages):
    first = messages[0] if isinstance(messages, list) and messages else {}
    content = getattr(first, "content", "") if not isinstance(first, dict) else str(first.get("content", ""))
    if "strict JSON extractor" in content:
        return (
            '{"schema_version":"world_extractor_v4","world_buckets_patch":{"offers":[{"text":"Oferta inicial 9000","confidence":0.8,"raw_text":"te doy 9000","source_turn":1}],'
            '"concessions":[],"constraints":[],"interests":[],"claims":[],"requests":[],"context":[]},'
            '"meta":{"negotiation_signal_detected":true,"extraction_quality":"high"}}'
        )
    return '{"response_text":"Puedo cerrar en 9.200€ si hacemos transferencia hoy.","asked_question":true,"requested_info_slots":["metodo_pago"],"tone_used":"neutral","followup_intent":"close","render_meta":{}}'


def _fake_plan_phase_policy(**_kwargs):
    decision = default_policy_decision()
    decision.update(
        {
            "policy_id": "tradeoff_offer",
            "micro_goal": "Concretar precio final y condiciones de pago",
            "why_short": "hay señal de cierre",
        }
    )
    phase_candidate = {
        "phase": "formalize",
        "confidence": 0.77,
        "reasons": ["price_anchor_seen"],
        "signals": [],
        "alternatives": [{"policy_id": "hold_position", "reason": "menos avance"}],
    }
    planner_meta = {
        "planner_llm_called": True,
        "planner_latency_ms": 37,
        "planner_failed": False,
        "planner_fallback_used": False,
    }
    return phase_candidate, decision, planner_meta


def _fake_update_belief_state(*_args, **_kwargs):
    return default_belief_state(), {"belief_latency_ms": 8, "belief_updater_invoked": True}


def test_trace_runtime_is_persisted_and_emitted_with_nodes_and_llm_calls(monkeypatch):
    monkeypatch.setenv("TRACE_LEVEL", "2")
    monkeypatch.setenv("TRACE_INCLUDE_INTERNALS", "1")

    deps = SimpleNamespace(
        execute=_fake_execute,
        plan_phase_policy=_fake_plan_phase_policy,
        update_belief_state=_fake_update_belief_state,
        summarize=None,
    )

    state = SessionState(user_id="u", session_id="s")
    state.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    state.progress_state = default_progress_state()

    run_negotiation_agent(state, "te doy 9000", deps=deps)

    trace_item = state.debug_trace[-1]
    runtime = trace_item.get("trace_runtime") or {}
    assert runtime
    assert runtime["nodes"]["world_updater"]["entered"] is True
    assert runtime["nodes"]["phase_policy_planner"]["entered"] is True
    assert runtime["nodes"]["executor"]["entered"] is True

    event = build_trace_event(
        user_id="u",
        session_id="s",
        session=state,
        trace_index=len(state.debug_trace) - 1,
        trace_item=trace_item,
    )

    assert event["timing"]["nodes"]["world_updater"]["entered"] is True
    assert event["timing"]["nodes"]["phase_policy_planner"]["total_ms"] > 0
    assert any(item.get("node") == "phase_policy_planner" for item in event["timing"]["llm_calls"])


def test_planner_llm_called_implies_planner_entry_in_llm_calls(monkeypatch):
    monkeypatch.setenv("TRACE_LEVEL", "2")
    monkeypatch.setenv("TRACE_INCLUDE_INTERNALS", "1")

    session = SessionState(user_id="u", session_id="s")
    session.last_updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
    trace_item = {
        "turn": 1,
        "planner_meta": {"planner_llm_called": True, "planner_latency_ms": 42, "planner_failed": False},
        "planner_debug": {"llm_call": {"planner_llm_called": True, "planner_latency_ms": 42}},
        "trace_runtime": {"nodes": {}, "llm_calls": []},
    }

    event = build_trace_event(user_id="u", session_id="s", session=session, trace_index=0, trace_item=trace_item)

    planner_calls = [x for x in event["timing"]["llm_calls"] if x.get("node") == "phase_policy_planner"]
    assert planner_calls
    assert planner_calls[0]["latency_ms"] > 0
