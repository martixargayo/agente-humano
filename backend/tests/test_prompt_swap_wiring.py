import json

import pytest

from negotiation.executor.render_executor import render_executor_output
from negotiation.phase_cards_extended import (
    OFFICIAL_PHASE_IDS,
    TOPICS_BY_PHASE,
    default_topic_for_phase,
    extract_topic_selected,
    get_phase_card_extended,
)
from negotiation.phase_policy_planner import _normalize_next_move_hint


def test_extract_topic_selected_regex_variants_inline_and_multiline():
    t1, s1 = extract_topic_selected('RESPUESTA: ok\nTEMA: "Motivo de venta (por qué ahora)"')
    assert t1 == "Motivo de venta (por qué ahora)"
    assert s1 == "hint_regex"

    t2, s2 = extract_topic_selected('RESPUESTA: ok MOVIMIENTO: avance TEMA: "Checklist: entrega y trámites"')
    assert t2 == "Checklist: entrega y trámites"
    assert s2 == "hint_regex"

    t3, s3 = extract_topic_selected("RESPUESTA: ok\nTEMA: Precio vs comodidad (fecha/recogida/papeleo)")
    assert t3 == "Precio vs comodidad (fecha/recogida/papeleo)"
    assert s3 == "hint_fallback"

    t4, s4 = extract_topic_selected("RESPUESTA: ok\nMOVIMIENTO: sin tema")
    assert t4 == ""
    assert s4 == "none"


@pytest.mark.parametrize("phase", OFFICIAL_PHASE_IDS)
def test_get_phase_card_extended_for_official_phases(phase):
    card, status = get_phase_card_extended(phase)
    assert status == "ok"
    assert card["phase"] == phase
    assert "do_text" in card and "tecnicas_text" in card and "evitar_text" in card and "question_policy" in card


def test_get_phase_card_extended_literal_content():
    card, _ = get_phase_card_extended("clima_humano")
    assert "Cálido y breve. “Persona primero”" in card["do_text"]
    assert "Micro-humor suave" in card["tecnicas_text"]
    assert "Hablar de precio, estado técnico o papeleo." in card["evitar_text"]
    assert card["topics"] == TOPICS_BY_PHASE["clima_humano"]


class _DepsSingle:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = 0
        self.last_messages = None

    def execute(self, messages):
        self.last_messages = messages
        out = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return json.dumps(out, ensure_ascii=False)


def _base_state(next_move_hint: str, phase: str = "clima_humano", user_message: str = "hola"):
    return {
        "planner_semantic_output": {
            "schema_version": "planner_semantic_v1",
            "phase": phase,
            "style": "psyplay_compact",
            "next_move_hint": next_move_hint,
            "what_not_to_repeat": [],
        },
        "user_message": user_message,
        "assistant_last_message": "prev",
        "recent_history_text": "Vendedor: hola",
        "speaker_of_user_message": "seller",
        "progress_state": {"phase_state": {"phase": "clima_humano"}},
        "effective_semantic_ledger": {
            "lo_que_ya_se_toco": [],
            "lo_que_ya_pregunte": [],
            "lo_que_falta_pero_no_insistire": [],
        },
    }


def _render_with_deps(state, deps):
    return render_executor_output(
        state,
        deps=deps,
        conversation_mode="negotiation",
        policy_pack_active="semantic",
        policy_id="semantic_ledger",
        persona_profile={},
        scene_profile={},
        style_contract={"style_id": "psyplay_compact", "max_words": 40, "max_questions": 1},
        constraints_struct={"max_questions": 1},
        strategy_summary={},
        memory_block="",
        world_state={},
        user_message=state["user_message"],
    )


def test_topic_with_question_marks_is_valid_for_tema():
    topic = "Historia ligera: ¿hace cuánto lo tienes?"
    state = _base_state(f'RESPUESTA: ok\nMOVIMIENTO: avance\nTEMA: "{topic}"', phase="clima_humano")
    out = _render_with_deps(
        state,
        _DepsSingle(
            [
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto, seguimos por texto.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                }
            ]
        ),
    )
    assert out["schema_version"] == "executor_v2"
    assert state["topic_selected"] == topic
    assert state["topic_selected_source"] == "hint_regex"


def test_invalid_topic_fallback_for_phase():
    state = _base_state('RESPUESTA: ok\nMOVIMIENTO: avance\nTEMA: "Motivo de venta (por qué ahora)"')
    out = _render_with_deps(
        state,
        _DepsSingle(
            [
                {
                    "schema_version": "executor_v2",
                    "response_text": "Perfecto, seguimos por texto.",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                }
            ]
        ),
    )
    assert out["schema_version"] == "executor_v2"
    assert state["topic_selected"] == default_topic_for_phase("clima_humano")
    assert state["topic_selected_source"] == "invalid_fallback"




def test_executor_render_meta_tracks_prev_phase_and_phase():
    state = _base_state('RESPUESTA: Hola\nMOVIMIENTO: avanzar\nTEMA: "Pequeño rapport: día / cómo está"', phase="descubrimiento_y_comprension")
    state["progress_state"] = {"phase_state": {"phase": "clima_humano"}}
    out = _render_with_deps(
        state,
        _DepsSingle([
            {
                "schema_version": "executor_v2",
                "response_text": "Perfecto, seguimos por texto.",
                "asked_question": False,
                "requested_info_slots": [],
                "tone_used": "neutral",
            }
        ]),
    )
    assert out["render_meta"]["prev_phase"] == "clima_humano"
    assert out["render_meta"]["phase"] == "descubrimiento_y_comprension"


def test_executor_schema_retry_first_invalid_second_valid():
    state = _base_state('RESPUESTA: Hola\nMOVIMIENTO: avanzar\nTEMA: "Pequeño rapport: día / cómo está"')
    deps = _DepsSingle(
        [
            {
                "phase": "clima_humano",
                "style": "psyplay_compact",
                "next_move_hint": "RESPUESTA: Hola",
            },
            {
                "schema_version": "executor_v2",
                "response_text": "Hola, ¿qué tal?",
                "asked_question": True,
                "requested_info_slots": ["saludo"],
                "tone_used": "friendly",
            },
        ]
    )
    out = _render_with_deps(state, deps)
    assert out["schema_version"] == "executor_v2"
    assert deps.calls == 2
    assert out["render_meta"]["schema_retry_count"] == 1
    assert out["render_meta"]["interrogative_retry_count"] == 0


def test_executor_schema_salvage_response_to_response_text():
    state = _base_state('RESPUESTA: Hola\nMOVIMIENTO: avanzar\nTEMA: "Pequeño rapport: día / cómo está"')
    deps = _DepsSingle(
        [
            {
                "schema_version": "executor_v2",
                "response": "Hola, ¿qué tal?",
                "asked_question": True,
                "requested_info_slots": ["saludo"],
                "tone_used": "friendly",
            }
        ]
    )
    out = _render_with_deps(state, deps)
    assert out["schema_version"] == "executor_v2"
    assert out["response_text"].startswith("Hola")
    assert out["render_meta"]["schema_salvage"] is True


def test_executor_question_slots_coherence_enforced_when_question_present():
    state = _base_state('OBJECTIVE_DELTA: improve_price\nTACTIC: tradeoff\nRESPUESTA: Hola\nMOVIMIENTO: avanzar\nTEMA: "Pequeño rapport: día / cómo está"')
    out = _render_with_deps(
        state,
        _DepsSingle(
            [
                {
                    "schema_version": "executor_v2",
                    "response_text": "¿Cuál sería tu precio final?",
                    "asked_question": False,
                    "requested_info_slots": [],
                    "tone_used": "neutral",
                }
            ]
        ),
    )
    assert out["asked_question"] is True
    assert out["requested_info_slots"]


def test_executor_wiring_injects_single_extended_phase_card():
    state = _base_state('RESPUESTA: ok\nMOVIMIENTO: avance\nTEMA: "Último ajuste para cerrar hoy"', phase="concesiones_y_ajuste_final")
    deps = _DepsSingle(
        [
            {
                "schema_version": "executor_v2",
                "response_text": "Perfecto, seguimos por texto.",
                "asked_question": False,
                "requested_info_slots": [],
                "tone_used": "neutral",
            }
        ]
    )
    _render_with_deps(state, deps)
    rendered = str(deps.last_messages[1].content)
    assert "PHASE_CARD_EXTENDIDA" in rendered
    assert "prev_phase: clima_humano" in rendered
    assert "phase: concesiones_y_ajuste_final" in rendered
    assert "TOPICS_VALIDOS:" in rendered
    assert "clima_humano" not in rendered.split("PHASE_CARD_EXTENDIDA", 1)[1]


def test_planner_postcheck_removes_questions_outside_tema():
    normalized, changed = _normalize_next_move_hint(
        "clima_humano",
        'RESPUESTA: Hola, ¿cómo estás? MOVIMIENTO: Validar tono y abrir. TEMA: "clima_humano"',
    )
    assert changed is True
    assert "RESPUESTA:" in normalized and "MOVIMIENTO:" in normalized and "TEMA:" in normalized
    assert "PREGUNTA:" not in normalized
    for line in normalized.splitlines():
        if line.startswith("TEMA:"):
            continue
        if line.startswith("RESPUESTA:") or line.startswith("MOVIMIENTO:"):
            assert "?" not in line and "¿" not in line


def test_planner_postcheck_keeps_five_lines_when_no_question():
    normalized, _ = _normalize_next_move_hint(
        "clima_humano",
        'RESPUESTA: Gracias por escribir\nMOVIMIENTO: Mantengo tono cordial y avanzo\nTEMA: "Pequeño rapport: día / cómo está"',
    )
    lines = normalized.splitlines()
    assert len(lines) == 5
    assert lines[0].startswith("OBJECTIVE_DELTA:")
    assert lines[1].startswith("TACTIC:")
    assert all(not ln.startswith("PREGUNTA:") for ln in lines)


def test_planner_postcheck_normalizes_objective_delta_and_tactic():
    normalized, _ = _normalize_next_move_hint(
        "propuesta_creativa",
        'RESPUESTA: validar paso MOVIMIENTO: avanzar cierre TEMA: "Señal + fecha de pago (todo registrado)"',
    )
    assert "OBJECTIVE_DELTA:" in normalized
    assert "TACTIC:" in normalized


def test_planner_phase_jump_not_forced_to_plus_one():
    normalized, _ = _normalize_next_move_hint(
        "formalizacion_del_acuerdo",
        'RESPUESTA: Perfecto\nMOVIMIENTO: Confirmamos cierre\nTEMA: "Checklist: entrega y trámites"',
    )
    assert 'TEMA: "Checklist: entrega y trámites"' in normalized
