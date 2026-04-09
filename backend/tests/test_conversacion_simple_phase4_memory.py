from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import StructuredBrainCall, run_conversacion_simple_turn
from conversacion_simple.services import build_conversacion_simple_turn_context
from sessions.state import SessionState


def _bind(state: SessionState, context_id: str = "baseline") -> None:
    state.world_state["conversacion_simple_context"] = {
        "flow_id": "conversacion_simple",
        "context_id": context_id,
        "context_version": "1.0.0",
    }


def _valid_brain_output(event_summary: str = "hecho") -> dict:
    return {
        "schema_version": "brain.v1",
        "status": "deliver",
        "assistant_response": {"text": "respuesta brain"},
        "state_patch": {
            "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "avanzar"},
            "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "resumen"},
            "memory_episodic_append": [
                {"event_type": "important_fact", "event_summary": event_summary, "turn_id": "t1"}
            ],
        },
        "observability": {"rationale_summary": "ok"},
    }


def _run_turn(monkeypatch, state: SessionState, *, event_summary: str = "hecho", **config_updates):
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output(event_summary=event_summary), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(update=config_updates)
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    return run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context), config


def test_recent_dialogue_trimming_operational(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    for _ in range(4):
        (_reply, updated, _meta), config = _run_turn(
            monkeypatch,
            state,
            context_limit_turns=2,
            keep_last_n_turns=2,
        )
    assert len(updated.world_state[config.recent_dialogue_key]) == 4


def test_compaction_is_scheduled_when_threshold_exceeded(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    (_reply, updated, _), config = _run_turn(
        monkeypatch,
        state,
        episodic_compaction_trigger_count=1,
        max_episodic_high_resolution_items=1,
    )
    trace = updated.world_state[config.traces_key][-1]
    assert "memory_compaction_scheduled" in trace["memory_observability"]


def test_deferred_compaction_does_not_block_turn(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    (reply, _updated, _), _config = _run_turn(monkeypatch, state, episodic_compaction_trigger_count=1)
    assert reply == "respuesta brain"


def test_fallback_deterministic_after_retry_budget(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    (_reply, updated, _), config = _run_turn(
        monkeypatch,
        state,
        episodic_compaction_trigger_count=1,
        maintenance_force_failure=True,
        maintenance_retry_limit=1,
        max_episodic_high_resolution_items=0,
    )
    canonical = updated.world_state[config.memory_key]
    assert canonical["memory_maintenance"]["last_mode"] == "deterministic_fallback"


def test_memory_compacted_summary_updates(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    (_reply, updated, _), config = _run_turn(
        monkeypatch,
        state,
        episodic_compaction_trigger_count=1,
        max_episodic_high_resolution_items=0,
    )
    assert updated.world_state[config.memory_key]["memory_compacted_summary"]


def test_memory_observability_fields_in_trace(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    (_reply, updated, _), config = _run_turn(monkeypatch, state, episodic_compaction_trigger_count=1)
    obs = updated.world_state[config.traces_key][-1]["memory_observability"]
    required = {
        "memory_recent_dialogue_count_before",
        "memory_recent_dialogue_count_after",
        "memory_recent_dialogue_trimmed_count",
        "memory_episodic_count_before",
        "memory_episodic_count_after",
        "memory_compaction_scheduled",
        "memory_compaction_mode",
        "memory_compaction_status",
        "memory_compaction_reason",
        "memory_compacted_summary_chars_before",
        "memory_compacted_summary_chars_after",
        "memory_growth_anomaly_flag",
    }
    assert required.issubset(set(obs.keys()))


def test_long_conversation_stability(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    config = None
    for idx in range(20):
        (_reply, updated, _), config = _run_turn(
            monkeypatch,
            state,
            event_summary=f"fact-{idx}",
            context_limit_turns=10,
            keep_last_n_turns=5,
            episodic_compaction_trigger_count=4,
            max_episodic_high_resolution_items=5,
        )
    assert len(updated.world_state[config.recent_dialogue_key]) <= 20
    assert len(updated.world_state[config.memory_key]["memory_episodic"]) <= 5


def test_runtime_base_still_returns_single_llm_meta(monkeypatch) -> None:
    state = SessionState(user_id="u", session_id="s")
    _bind(state)
    (_reply, _updated, meta), _ = _run_turn(monkeypatch, state)
    assert meta["pipeline_topology"] == "single_llm"
    assert meta["node_names"] == ["brain"]
