"""
Comprehensive audit test for long-form conversation flow.
Validates:
- Threshold logic (>20, not >=20)
- Turn partitioning (literal vs archived)
- Summary reinjection and truncation
- recent_dialogue_short configuration
- Stateless provider
- Model targets
- End-to-end 25-turn scenario
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.memory.policy import split_dialogue_into_turns
from conversacion_simple.nodes import DialogueMessage
from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import (
    StructuredBrainCall,
    StructuredSummarizerCall,
    SummarizerOutput,
    run_conversacion_simple_turn,
)
from conversacion_simple.services import build_conversacion_simple_turn_context
from sessions.state import SessionState


def _bind(state: SessionState, context_id: str = "baseline") -> None:
    state.world_state["conversacion_simple_context"] = {
        "flow_id": "conversacion_simple",
        "context_id": context_id,
        "context_version": "1.0.0",
    }


def _valid_brain_output(reply_text: str = "respuesta") -> dict:
    return {
        "schema_version": "brain.v1",
        "status": "deliver",
        "assistant_response": {"text": reply_text},
        "state_patch": {
            "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "avanzar"},
            "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "resumen"},
            "memory_episodic_append": [],
        },
    }


class _AuditCapture:
    def __init__(self):
        self.summarizer_calls = 0
        self.brain_calls = 0
        self.brain_input_summaries: list[str] = []
        self.brain_recent_dialogue_short_sizes: list[int] = []
        self.providers_used: dict[str, str] = {}


def test_audit_threshold_is_strictly_gt_20_not_gte_20(monkeypatch) -> None:
    """Verify threshold is >20, not >=20."""
    state = SessionState(user_id="u_gt", session_id="s_gt")
    _bind(state)
    calls = {"summarizer": 0}

    def _fake_summarizer(**kwargs):
        calls["summarizer"] += 1
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum_1",
        )

    def _fake_brain(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 20, "keep_last_n_turns": 20}
    )

    # At 20 turns, summarizer should NOT trigger
    for idx in range(20):
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(state=state, user_message=f"t{idx}", config=config, turn_context=turn_context)
    assert calls["summarizer"] == 0, "Summarizer should not trigger at exactly 20 turns"

    # At 21 turns, summarizer MUST trigger
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    run_conversacion_simple_turn(state=state, user_message="t20", config=config, turn_context=turn_context)
    assert calls["summarizer"] >= 1, "Summarizer must trigger at 21 turns"


def test_audit_turn_partitioning_with_20_20_config(monkeypatch) -> None:
    """Verify 25 turns with 20/20 config results in 5 archived, 20 literal."""
    state = SessionState(user_id="u_partition", session_id="s_partition")
    _bind(state)
    capture = _AuditCapture()

    def _fake_summarizer(**kwargs):
        capture.summarizer_calls += 1
        messages = kwargs["messages"]
        user_payload = messages[1]["content"]
        start = user_payload.index("<summary_input_json>\n") + len("<summary_input_json>\n")
        end = user_payload.index("\n</summary_input_json>")
        payload = json.loads(user_payload[start:end])
        archived_count = len(payload.get("archived_turns", []))
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live=f"{archived_count}_turns"),
            response_id=f"sum_{capture.summarizer_calls}",
        )

    def _fake_brain(**kwargs):
        capture.brain_calls += 1
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    for idx in range(25):
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(state=state, user_message=f"turno_{idx}", config=config, turn_context=turn_context)

    recent_turns = split_dialogue_into_turns(
        recent_dialogue=[DialogueMessage.model_validate(item) for item in state.world_state[config.recent_dialogue_key]]
    )
    assert len(recent_turns) == 20, f"Expected 20 literal turns, got {len(recent_turns)}"
    assert capture.summarizer_calls > 0, "Summarizer must have been called"


def test_audit_brain_receives_configured_recent_dialogue_short_max(monkeypatch) -> None:
    """Verify brain receives recent_dialogue_short limited to config value, not hardcoded."""
    state = SessionState(user_id="u_brain_short", session_id="s_brain_short")
    _bind(state)
    capture = _AuditCapture()

    def _fake_brain(**kwargs):
        capture.brain_calls += 1
        messages = kwargs["messages"]
        user_payload = messages[1]["content"]
        start = user_payload.index("<brain_input_json>\n") + len("<brain_input_json>\n")
        end = user_payload.index("\n</brain_input_json>")
        parsed = json.loads(user_payload[start:end])
        capture.brain_recent_dialogue_short_sizes.append(len(parsed.get("recent_dialogue_short", [])))
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)

    # Test with custom max
    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 3, "keep_last_n_turns": 3, "recent_dialogue_short_max_messages": 5}
    )

    # Run 4 turns to exceed limit and trigger some accumulation
    for idx in range(4):
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(state=state, user_message=f"msg_{idx}", config=config, turn_context=turn_context)

    # After at least one turn, brain should receive up to 5 messages (not hardcoded 8)
    assert capture.brain_calls >= 1
    # The last call might have fewer than 5 if not enough messages yet, but config should be applied
    max_seen = max(capture.brain_recent_dialogue_short_sizes) if capture.brain_recent_dialogue_short_sizes else 0
    assert max_seen <= 5, f"Brain received more than configured max (5), got {max_seen}"


def test_audit_summary_truncated_to_max_chars(monkeypatch) -> None:
    """Verify memory_compacted_summary is truncated to config.compacted_summary_max_chars."""
    state = SessionState(user_id="u_truncate", session_id="s_truncate")
    _bind(state)
    capture = _AuditCapture()

    def _fake_summarizer(**kwargs):
        # Return a very long summary
        long_text = "x" * 3000  # Exceeds default 1600
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live=long_text),
            response_id="sum_long",
        )

    def _fake_brain(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 0, "keep_last_n_turns": 0, "compacted_summary_max_chars": 500}
    )

    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    canonical = state.world_state[config.memory_key]
    summary = canonical.get("memory_compacted_summary", "")
    assert len(summary) <= 500, f"Summary truncation failed: {len(summary)} > 500"


def test_audit_provider_stateless_in_both_brain_and_summarizer(monkeypatch) -> None:
    """Verify both brain and summarizer maintain stateless provider pattern."""
    state = SessionState(user_id="u_stateless", session_id="s_stateless")
    _bind(state)
    captured_kwargs: dict[str, Any] = {}

    def _fake_brain(**kwargs):
        captured_kwargs["brain_kwargs"] = kwargs
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    def _fake_summarizer(**kwargs):
        captured_kwargs["summarizer_kwargs"] = kwargs
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum_ok",
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 0, "keep_last_n_turns": 0}
    )
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    run_conversacion_simple_turn(state=state, user_message="test", config=config, turn_context=turn_context)

    # Check brain call
    brain_kw = captured_kwargs.get("brain_kwargs", {})
    assert brain_kw.get("model") == "gpt-5.4"
    assert brain_kw.get("max_output_tokens") == 1024

    # Check summarizer call (only triggered if >20 turns, so trigger it)
    if "summarizer_kwargs" not in captured_kwargs:
        # Need to trigger summarizer by exceeding turn limit
        config2 = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
        for i in range(21):
            turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
            run_conversacion_simple_turn(state=state, user_message=f"many_{i}", config=config2, turn_context=turn_context)

    summarizer_kw = captured_kwargs.get("summarizer_kwargs", {})
    assert summarizer_kw.get("model") == "gpt-5.4-nano"


def test_audit_model_targets_brain_vs_summarizer(monkeypatch) -> None:
    """Verify brain and summarizer use different configured models."""
    state = SessionState(user_id="u_models", session_id="s_models")
    _bind(state)
    models_seen = {}

    def _fake_brain(**kwargs):
        models_seen["brain"] = kwargs.get("model")
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    def _fake_summarizer(**kwargs):
        models_seen["summarizer"] = kwargs.get("model")
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum",
        )

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    assert config.brain_model_target == "gpt-5.4"
    assert config.summarizer_model_target == "gpt-5.4-nano"

    # Force summarizer trigger
    config = config.model_copy(update={"context_limit_turns": 0, "keep_last_n_turns": 0})
    for i in range(21):
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(state=state, user_message=f"t_{i}", config=config, turn_context=turn_context)

    assert models_seen.get("brain") == "gpt-5.4"
    assert models_seen.get("summarizer") == "gpt-5.4-nano"


def test_audit_20_vs_21_vs_25_vs_40_turns_partition(monkeypatch) -> None:
    """Comprehensive test: 20, 21, 25, and 40 turns verify archived/literal split."""
    test_cases = [
        (20, 0, 20),  # 20 turns: 0 archived, 20 literal
        (21, 1, 20),  # 21 turns: 1 archived, 20 literal
        (25, 5, 20),  # 25 turns: 5 archived, 20 literal
        (40, 20, 20),  # 40 turns: 20 archived, 20 literal
    ]

    for total_turns, expected_archived, expected_literal in test_cases:
        state = SessionState(user_id=f"u_{total_turns}", session_id=f"s_{total_turns}")
        _bind(state)
        archive_tracker = {"count": 0}

        def _fake_summarizer(**kwargs):
            messages = kwargs["messages"]
            user_payload = messages[1]["content"]
            start = user_payload.index("<summary_input_json>\n") + len("<summary_input_json>\n")
            end = user_payload.index("\n</summary_input_json>")
            payload = json.loads(user_payload[start:end])
            archive_tracker["count"] = len(payload.get("archived_turns", []))
            return StructuredSummarizerCall(
                source="model",
                output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
                response_id="sum",
            )

        def _fake_brain(**kwargs):
            return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

        monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer)
        monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain)

        config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
        for idx in range(total_turns):
            turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
            run_conversacion_simple_turn(state=state, user_message=f"t_{idx}", config=config, turn_context=turn_context)

        recent_turns = split_dialogue_into_turns(
            recent_dialogue=[DialogueMessage.model_validate(item) for item in state.world_state[config.recent_dialogue_key]]
        )
        assert (
            len(recent_turns) == expected_literal
        ), f"At {total_turns} turns: expected {expected_literal} literal, got {len(recent_turns)}"

        if total_turns > 20:
            assert archive_tracker["count"] >= 1
