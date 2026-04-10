from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.memory.policy import split_dialogue_into_turns, trim_recent_dialogue_by_turns
from conversacion_simple.nodes import DialogueMessage
from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import (
    StructuredBrainCall,
    StructuredSummarizerCall,
    SummarizerOutput,
    _render_structured_summary,
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


def test_trim_recent_dialogue_by_turns_respects_turn_boundaries() -> None:
    dialogue = [
        DialogueMessage(role="user", text="u1"),
        DialogueMessage(role="assistant", text="a1"),
        DialogueMessage(role="assistant", text="tool_result_like"),
        DialogueMessage(role="user", text="u2"),
        DialogueMessage(role="assistant", text="a2"),
    ]
    kept, archived_turns, metrics = trim_recent_dialogue_by_turns(
        recent_dialogue=dialogue,
        context_limit_turns=1,
        keep_last_n_turns=1,
    )
    assert len(split_dialogue_into_turns(recent_dialogue=kept)) == 1
    assert kept[0].text == "u2"
    assert kept[-1].text == "a2"
    assert len(archived_turns) == 1
    assert metrics["memory_recent_turns_archived_count"] == 1


@pytest.mark.parametrize(
    ("turn_count", "expected_archived", "expected_literal"),
    [
        (20, 0, 20),
        (21, 1, 20),
        (25, 5, 20),
        (40, 20, 20),
    ],
)
def test_turn_partition_exact_counts_with_limit_20_keep_20(turn_count: int, expected_archived: int, expected_literal: int) -> None:
    dialogue: list[DialogueMessage] = []
    for idx in range(turn_count):
        dialogue.append(DialogueMessage(role="user", text=f"u{idx}"))
        dialogue.append(DialogueMessage(role="assistant", text=f"a{idx}"))
    kept, archived_turns, _metrics = trim_recent_dialogue_by_turns(
        recent_dialogue=dialogue,
        context_limit_turns=20,
        keep_last_n_turns=20,
    )
    kept_turns = split_dialogue_into_turns(recent_dialogue=kept)
    assert len(archived_turns) == expected_archived
    assert len(kept_turns) == expected_literal


def test_summarizer_stage_triggers_and_reinjects_summary(monkeypatch) -> None:
    state = SessionState(user_id="u_sum", session_id="s_sum")
    _bind(state)
    capture: dict[str, object] = {"summarizer_calls": 0, "brain_input_summary": None}

    def _fake_summarizer_call(**kwargs):
        capture["summarizer_calls"] = int(capture["summarizer_calls"]) + 1
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(
                schema_version="memory_summary.v1",
                situation_live="negociación activa",
            ),
            response_id="sum_resp_1",
        )

    def _fake_brain_call(**kwargs):
        messages = kwargs["messages"]
        user_payload = messages[1]["content"]
        start = user_payload.index("<brain_input_json>\n") + len("<brain_input_json>\n")
        end = user_payload.index("\n</brain_input_json>")
        parsed = json.loads(user_payload[start:end])
        capture["brain_input_summary"] = parsed.get("memory_compacted_summary")
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer_call)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain_call)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 1, "keep_last_n_turns": 1}
    )
    for idx in range(3):
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(
            state=state,
            user_message=f"turno {idx}",
            config=config,
            turn_context=turn_context,
        )

    assert int(capture["summarizer_calls"]) >= 1
    summary = str(capture["brain_input_summary"] or "")
    assert "negociación activa" in summary
    recent = state.world_state[config.recent_dialogue_key]
    assert len(split_dialogue_into_turns(recent_dialogue=[DialogueMessage.model_validate(x) for x in recent])) <= 1


def test_summarizer_trigger_threshold_is_strictly_greater_than_20(monkeypatch) -> None:
    state = SessionState(user_id="u_threshold", session_id="s_threshold")
    _bind(state)
    capture: dict[str, int] = {"summarizer_calls": 0}

    def _fake_summarizer_call(**kwargs):
        capture["summarizer_calls"] += 1
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum_resp",
        )

    def _fake_brain_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer_call)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain_call)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 20, "keep_last_n_turns": 4}
    )
    # 19 turns: no summarizer
    for idx in range(19):
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(state=state, user_message=f"t{idx}", config=config, turn_context=turn_context)
    assert capture["summarizer_calls"] == 0

    # 20 turns exact: still no summarizer
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    run_conversacion_simple_turn(state=state, user_message="t19", config=config, turn_context=turn_context)
    assert capture["summarizer_calls"] == 0

    # 21 turns: now summarizer must trigger
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    run_conversacion_simple_turn(state=state, user_message="t20", config=config, turn_context=turn_context)
    assert capture["summarizer_calls"] >= 1


def test_keep_last_n_turns_are_preserved_verbatim_and_current_user_turn_survives(monkeypatch) -> None:
    state = SessionState(user_id="u_keep", session_id="s_keep")
    _bind(state)
    captured: dict[str, object] = {"recent_dialogue_short": [], "user_turn": None}

    def _fake_summarizer_call(**kwargs):
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum_resp",
        )

    def _fake_brain_call(**kwargs):
        user_payload = kwargs["messages"][1]["content"]
        start = user_payload.index("<brain_input_json>\n") + len("<brain_input_json>\n")
        end = user_payload.index("\n</brain_input_json>")
        parsed = json.loads(user_payload[start:end])
        captured["recent_dialogue_short"] = parsed.get("recent_dialogue_short", [])
        captured["user_turn"] = parsed.get("user_turn")
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer_call)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain_call)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 2, "keep_last_n_turns": 2}
    )
    for msg in ["u1", "u2", "u3"]:
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(state=state, user_message=msg, config=config, turn_context=turn_context)

    recent_turns = split_dialogue_into_turns(
        recent_dialogue=[DialogueMessage.model_validate(item) for item in state.world_state[config.recent_dialogue_key]]
    )
    assert len(recent_turns) == 2
    assert recent_turns[-1][0].text == "u3"
    assert isinstance(captured["user_turn"], dict) and captured["user_turn"]["raw_text"] == "u3"
    assert captured["recent_dialogue_short"]


def test_prompts_and_calls_are_separated_between_summarizer_and_brain(monkeypatch) -> None:
    state = SessionState(user_id="u_prompts", session_id="s_prompts")
    _bind(state)
    capture: dict[str, object] = {"summarizer_dev": None, "brain_dev": None, "brain_payload": None}

    def _fake_summarizer_call(**kwargs):
        capture["summarizer_dev"] = kwargs["messages"][0]["content"]
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum_resp",
        )

    def _fake_brain_call(**kwargs):
        capture["brain_dev"] = kwargs["messages"][0]["content"]
        user_payload = kwargs["messages"][1]["content"]
        start = user_payload.index("<brain_input_json>\n") + len("<brain_input_json>\n")
        end = user_payload.index("\n</brain_input_json>")
        capture["brain_payload"] = json.loads(user_payload[start:end])
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer_call)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain_call)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True).model_copy(
        update={"context_limit_turns": 0, "keep_last_n_turns": 0}
    )
    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    run_conversacion_simple_turn(state=state, user_message="hola", config=config, turn_context=turn_context)

    assert isinstance(capture["summarizer_dev"], str) and "summarizer operativo" in str(capture["summarizer_dev"]).lower()
    assert isinstance(capture["brain_dev"], str) and "[ROLE] brain" in str(capture["brain_dev"])
    assert capture["summarizer_dev"] != capture["brain_dev"]
    assert "manda lo reciente" in str(capture["brain_dev"]).lower()
    payload = capture["brain_payload"] if isinstance(capture["brain_payload"], dict) else {}
    assert "memory_compacted_summary" in payload
    assert "recent_dialogue_short" in payload


def test_structured_summary_preserves_negotiation_keys_for_reinjection() -> None:
    output = SummarizerOutput(
        schema_version="memory_summary.v1",
        situation_live="Hay propuesta viva",
        active_proposal="Bloque B propone 16:30-18:00",
        latest_offer_each_side=["A: 17:00-18:00", "B: 16:30-18:00"],
        concessions_accumulated=["B acepta recortar 30 min"],
        open_items=["confirmar desmontaje"],
        closed_items=["duración mínima"],
        operative_constraints=["desmontaje 15 min"],
        fixed_time_calculations=["fin real 18:15"],
        operative_question_live="¿quién absorbe coordinación final?",
        sensitive_info_exposed=["dependencia de proveedor externo"],
        agreement_progress="casi_acuerdo",
        pending_inconsistencies=["fin 18:00 vs desmontaje 15m"],
        uncertainties=["falta validación legal"],
    )
    rendered = _render_structured_summary(output)
    parsed = json.loads(rendered)
    assert parsed["active_proposal"] == "Bloque B propone 16:30-18:00"
    assert "confirmar desmontaje" in parsed["open_items"]
    assert "dependencia de proveedor externo" in parsed["sensitive_info_exposed"]
    assert parsed["agreement_progress"] == "casi_acuerdo"


def test_model_targets_default_and_are_used(monkeypatch) -> None:
    state = SessionState(user_id="u_models", session_id="s_models")
    _bind(state)
    seen: dict[str, str] = {}

    def _fake_summarizer_call(**kwargs):
        seen["summarizer_model"] = kwargs["model"]
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum_resp",
        )

    def _fake_brain_call(**kwargs):
        seen["brain_model"] = kwargs["model"]
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer_call)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain_call)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    assert config.brain_model_target == "gpt-5.4"
    assert config.summarizer_model_target == "gpt-5.4-nano"
    assert config.context_limit_turns == 20
    assert config.keep_last_n_turns == 20

    turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
    run_conversacion_simple_turn(
        state=state,
        user_message="primer turno",
        config=config.model_copy(update={"context_limit_turns": 0, "keep_last_n_turns": 0}),
        turn_context=turn_context,
    )

    assert seen["brain_model"] == "gpt-5.4"
    assert seen["summarizer_model"] == "gpt-5.4-nano"


def test_pipeline_with_25_turns_keeps_20_verbatim_and_summarizes_5(monkeypatch) -> None:
    state = SessionState(user_id="u_25", session_id="s_25")
    _bind(state)
    capture = {"archived_total": 0}

    def _fake_summarizer_call(**kwargs):
        turns = kwargs["messages"][1]["content"]
        parsed_start = turns.index("<summary_input_json>\n") + len("<summary_input_json>\n")
        parsed_end = turns.index("\n</summary_input_json>")
        payload = json.loads(turns[parsed_start:parsed_end])
        capture["archived_total"] += len(payload.get("archived_turns", []))
        return StructuredSummarizerCall(
            source="model",
            output=SummarizerOutput(schema_version="memory_summary.v1", situation_live="ok"),
            response_id="sum_resp",
        )

    def _fake_brain_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_valid_brain_output("ok"), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_summarizer_structured", _fake_summarizer_call)
    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_brain_call)

    config = build_conversacion_simple_pipeline_config(context_id="baseline", stateful=True)
    for idx in range(25):
        turn_context = build_conversacion_simple_turn_context(state=state, entrypoint="/tests", requested_context_id="baseline")
        run_conversacion_simple_turn(state=state, user_message=f"turno_{idx}", config=config, turn_context=turn_context)

    recent_turns = split_dialogue_into_turns(
        recent_dialogue=[DialogueMessage.model_validate(item) for item in state.world_state[config.recent_dialogue_key]]
    )
    assert len(recent_turns) == 20
    assert capture["archived_total"] == 5
