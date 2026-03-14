from __future__ import annotations

from pathlib import Path

from evaluacion.contracts.models import (
    CoreRunnerInputV1,
    FeedbackReportCoreV1,
    KeyMoment,
)
from evaluacion.engine.flow_config import CORE_MODEL
from evaluacion.engine.runners.common import load_prompt_text, run_structured

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "core_evaluator_prompt.txt"


def _fallback_output(core_input: CoreRunnerInputV1) -> FeedbackReportCoreV1:
    turns = core_input.conversation.turns
    safe_idx = turns[0].turn_index if turns else 1
    safe_excerpt = turns[0].user_text[:140] if turns else "Sin evidencia suficiente."

    blocks = [
        {
            "block_id": "comprension_exploracion",
            "title": "Comprensión y exploración",
            "status_visual": "mejorable",
            "score_0_100": 62,
            "checks": [{"polarity": "check", "micro_explanation": "Exploración inicial detectada.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "Conviene profundizar más en preguntas clave.",
        },
        {
            "block_id": "comunicacion_clima",
            "title": "Comunicación y clima",
            "status_visual": "correcto",
            "score_0_100": 70,
            "checks": [{"polarity": "check", "micro_explanation": "Tono conversacional estable.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "Buena base de comunicación.",
        },
        {
            "block_id": "movimiento_tactico",
            "title": "Movimiento táctico",
            "status_visual": "mejorable",
            "score_0_100": 64,
            "checks": [{"polarity": "cross", "micro_explanation": "Faltan contrapartidas explícitas.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "Necesita mayor claridad táctica.",
        },
        {
            "block_id": "cierre_avance",
            "title": "Cierre y avance",
            "status_visual": "mejorable",
            "score_0_100": 66,
            "checks": [{"polarity": "check", "micro_explanation": "Hay intención de avance.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "Avance parcial sin cierre sólido.",
        },
    ]

    return FeedbackReportCoreV1(
        schema_version="feedback_report_core.v1",
        score_global_100=66,
        stars_0_5=3.3,
        interaction_outcome="partial_progress" if core_input.conversation_stats.turn_count >= 6 else "no_agreement",
        summary_2_3_lines=f"Se observa progreso conversacional con margen de mejora táctica. Ejemplo: {safe_excerpt}",
        evaluation_blocks=blocks,
        best_moment=KeyMoment(turn_index=safe_idx, why="Hubo señal de avance.", impact="Mejoró la alineación."),
        most_delicate_moment=KeyMoment(turn_index=safe_idx, why="Faltó precisión.", impact="Generó ambigüedad."),
        turning_point=KeyMoment(turn_index=safe_idx, why="Cambio de tono negociador.", impact="Reorientó la conversación."),
        recommendations_general=["Haz preguntas más específicas antes de proponer cierre."],
        correction_cases=[
            {
                "turn_index": safe_idx,
                "original_excerpt": safe_excerpt,
                "better_rephrase": "¿Qué condición concreta te permitiría cerrar hoy?",
                "expected_effect": "Incrementa claridad y foco en acuerdo.",
            }
        ],
        strengths_to_repeat=["Mantener tono dialogante."],
        next_focus="Conectar oferta y contrapartida de forma explícita.",
        recommended_closing_phrase="Si te encaja, cerramos en estas condiciones y confirmamos ahora.",
    )


def run_core_evaluator(core_input: CoreRunnerInputV1) -> tuple[FeedbackReportCoreV1, str]:
    prompt = load_prompt_text(PROMPT_PATH)
    parsed = run_structured(
        model=CORE_MODEL,
        developer_prompt=prompt,
        user_payload=core_input.model_dump(mode="json"),
        output_model=FeedbackReportCoreV1,
        schema_name="feedback_report_core_v1",
    )
    if parsed is None:
        return _fallback_output(core_input), "fallback_no_api_key"
    return FeedbackReportCoreV1.model_validate(parsed), "model"
