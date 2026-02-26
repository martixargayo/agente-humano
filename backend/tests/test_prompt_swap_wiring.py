import json
import pytest

from negotiation.executor.render_executor import render_executor_output
from negotiation.phase_cards_extended import (
    extract_topic_selected,
    get_phase_card_extended,
    default_topic_for_phase,
    OFFICIAL_PHASE_IDS,
)
from negotiation.schemas import default_progress_state, default_world_state


def test_extract_topic_selected_regex_variants():
    t1, s1 = extract_topic_selected('RESPUESTA: ok\nTEMA: "Motivo de venta (por qué ahora)"')
    assert t1 == "Motivo de venta (por qué ahora)"
    assert s1 == "hint_regex"

    t2, s2 = extract_topic_selected('RESPUESTA: ok\nTEMA: “Checklist: entrega y trámites”')
    assert t2 == "Checklist: entrega y trámites"
    assert s2 == "hint_regex"

    t3, s3 = extract_topic_selected('RESPUESTA: ok\nTEMA: Precio vs comodidad (fecha/recogida/papeleo)')
    assert t3 == "Precio vs comodidad (fecha/recogida/papeleo)"
    assert s3 == "hint_fallback"

    t4, s4 = extract_topic_selected('RESPUESTA: ok\nMOVIMIENTO: sin tema')
    assert t4 == ""
    assert s4 == "none"


@pytest.mark.parametrize("phase", OFFICIAL_PHASE_IDS)
def test_get_phase_card_extended_for_official_phases(phase):
    card, status = get_phase_card_extended(phase)
    assert status == "ok"
    assert card["phase"] == phase
    assert "do" in card and "avoid" in card and "question_policy" in card


def test_get_phase_card_extended_fallback():
    card, status = get_phase_card_extended("fase_invalida")
    assert status == "fallback"
    assert card["phase"] == "clima_humano"


def test_default_topic_for_phase_and_missing():
    assert default_topic_for_phase("clima_humano") != "sin_tema"
    assert default_topic_for_phase("fase_invalida") == "sin_tema"


class _DepsRetryTextOnly:
    def __init__(self):
        self.calls = 0

    def execute(self, _messages):
        self.calls += 1
        if self.calls == 1:
            return json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto, muéstrame el papel y te digo.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "schema_version": "executor_v2",
                "response_text": "Perfecto, ¿qué documentación tienes al día por texto?",
                "asked_question": True,
                "requested_info_slots": ["documentacion"],
                "tone_used": "neutral",
                "followup_intent": None,
                "render_meta": {},
            },
            ensure_ascii=False,
        )


@pytest.mark.parametrize("phase", OFFICIAL_PHASE_IDS)
def test_integration_phase_topic_wiring_with_and_without_tema(phase):
    deps = _DepsRetryTextOnly()
    progress = default_progress_state()
    state = {
        "progress_state": progress,
        "planner_semantic_output": {
            "schema_version": "planner_semantic_v1",
            "phase": phase,
            "style": "psyplay_compact",
            "next_move_hint": "RESPUESTA: ok\nMOVIMIENTO: avance\nTEMA: \"Motivo de venta (por qué ahora)\"",
            "what_not_to_repeat": [],
        },
        "user_message": "vale",
        "assistant_last_message": "prev",
        "recent_history_text": "Vendedor: hola",
        "speaker_of_user_message": "seller",
        "effective_semantic_ledger": {
            "lo_que_ya_se_toco": ["Motivo de venta comentado"],
            "lo_que_ya_pregunte": [],
            "lo_que_falta_pero_no_insistire": [],
        },
    }

    out = render_executor_output(
        state,
        deps=deps,
        conversation_mode="negotiation",
        policy_pack_active="semantic",
        policy_id="semantic_ledger",
        persona_profile={"style_id": "psyplay_compact"},
        scene_profile={},
        style_contract={"style_id": "psyplay_compact", "max_words": 40, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state=default_world_state(),
        user_message="vale",
    )
    assert out["schema_version"] == "executor_v2"
    assert state["phase_card_lookup_status"] in {"ok", "fallback"}
    assert state["topic_selected_source"] in {"hint_regex", "hint_fallback", "phase_default", "invalid_fallback", "none"}

    # caso sin TEMA para fallback
    state["planner_semantic_output"]["next_move_hint"] = "RESPUESTA: ok\nMOVIMIENTO: avance"
    out2 = render_executor_output(
        state,
        deps=deps,
        conversation_mode="negotiation",
        policy_pack_active="semantic",
        policy_id="semantic_ledger",
        persona_profile={"style_id": "psyplay_compact"},
        scene_profile={},
        style_contract={"style_id": "psyplay_compact", "max_words": 40, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state=default_world_state(),
        user_message="vale",
    )
    assert out2["schema_version"] == "executor_v2"
    assert state["topic_selected"]
    assert state["topic_selected_source"] in {"phase_default", "none", "hint_regex", "hint_fallback"}


def test_integration_human_first_question_case():
    class _Deps:
        def execute(self, _messages):
            return json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Sí, me encaja si cerramos hoy.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )

    state = {
        "progress_state": default_progress_state(),
        "planner_semantic_output": {
            "schema_version": "planner_semantic_v1",
            "phase": "concesiones_y_ajuste_final",
            "style": "psyplay_compact",
            "next_move_hint": "RESPUESTA: Sí me encaja.\nMOVIMIENTO: cierre condicionado.\nTEMA: \"Último ajuste para cerrar hoy\"",
            "what_not_to_repeat": [],
        },
        "user_message": "¿Te encaja si cerramos hoy?",
        "assistant_last_message": "prev",
        "recent_history_text": "Vendedor: ¿te encaja si cerramos hoy?",
        "speaker_of_user_message": "seller",
        "effective_semantic_ledger": {
            "lo_que_ya_se_toco": [],
            "lo_que_ya_pregunte": [],
            "lo_que_falta_pero_no_insistire": [],
        },
    }
    out = render_executor_output(
        state,
        deps=_Deps(),
        conversation_mode="negotiation",
        policy_pack_active="semantic",
        policy_id="semantic_ledger",
        persona_profile={"style_id": "psyplay_compact"},
        scene_profile={},
        style_contract={"style_id": "psyplay_compact", "max_words": 40, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state=default_world_state(),
        user_message=state["user_message"],
    )
    assert out["schema_version"] == "executor_v2"


def test_invalid_topic_fallback_for_phase():
    class _Deps:
        def execute(self, _messages):
            return json.dumps(
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto, seguimos por texto.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                    "followup_intent": None,
                    "render_meta": {},
                },
                ensure_ascii=False,
            )

    state = {
        "progress_state": default_progress_state(),
        "planner_semantic_output": {
            "schema_version": "planner_semantic_v1",
            "phase": "clima_humano",
            "style": "psyplay_compact",
            "next_move_hint": "RESPUESTA: ok\nMOVIMIENTO: avance\nTEMA: \"Motivo de venta (por qué ahora)\"",
            "what_not_to_repeat": [],
        },
        "user_message": "hola",
        "assistant_last_message": "prev",
        "recent_history_text": "Vendedor: hola",
        "speaker_of_user_message": "seller",
        "effective_semantic_ledger": {
            "lo_que_ya_se_toco": [],
            "lo_que_ya_pregunte": [],
            "lo_que_falta_pero_no_insistire": [],
        },
    }
    out = render_executor_output(
        state,
        deps=_Deps(),
        conversation_mode="negotiation",
        policy_pack_active="semantic",
        policy_id="semantic_ledger",
        persona_profile={"style_id": "psyplay_compact"},
        scene_profile={},
        style_contract={"style_id": "psyplay_compact", "max_words": 40, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state=default_world_state(),
        user_message="hola",
    )
    assert out["schema_version"] == "executor_v2"
    assert state["topic_selected"] == default_topic_for_phase("clima_humano")
    assert state["topic_selected_source"] == "invalid_fallback"
