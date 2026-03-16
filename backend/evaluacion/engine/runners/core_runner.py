from __future__ import annotations

from pathlib import Path

from evaluacion.contracts.models import CoreRunnerInputV1, FeedbackReportCoreV1, KeyMoment
from evaluacion.engine.flow_config import CORE_MODEL
from evaluacion.engine.runners.common import load_prompt_text, run_structured

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "core_evaluator_prompt.txt"


def _fallback_output(core_input: CoreRunnerInputV1) -> FeedbackReportCoreV1:
    turns = core_input.conversation.turns
    safe_idx = turns[0].turn_index if turns else 1
    safe_excerpt = turns[0].user_text[:140] if turns else "Sin evidencia suficiente."

    blocks = [
        {
            "block_id": "valores",
            "title": "Valores",
            "status_visual": "mejorable",
            "score_0_100": 62,
            "checks": [{"polarity": "check", "micro_explanation": "Exploración inicial detectada.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "Hay base ética, pero falta explicitar criterios estables para sostener propuestas.",
        },
        {
            "block_id": "vision",
            "title": "Visión",
            "status_visual": "correcto",
            "score_0_100": 70,
            "checks": [{"polarity": "check", "micro_explanation": "Tono conversacional estable.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "Se intuye rumbo, pero conviene concretar mejor objetivos y escenarios.",
        },
        {
            "block_id": "relacion",
            "title": "Relación",
            "status_visual": "mejorable",
            "score_0_100": 64,
            "checks": [{"polarity": "cross", "micro_explanation": "Faltan contrapartidas explícitas.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "La interacción mantiene tracción, aunque debe reforzar escucha y validación mutua.",
        },
        {
            "block_id": "proceso",
            "title": "Proceso",
            "status_visual": "mejorable",
            "score_0_100": 66,
            "checks": [{"polarity": "check", "micro_explanation": "Hay intención de avance.", "evidence_turn_indexes": [safe_idx]}],
            "block_verdict": "El método de avance existe, pero falta cerrar acuerdos con mayor precisión operativa.",
        },
    ]

    return FeedbackReportCoreV1(
        schema_version="feedback_report_core.v1",
        score_global_100=66,
        interaction_outcome="partial_progress" if core_input.conversation_stats.turn_count >= 6 else "no_agreement",
        summary_2_3_lines=f"Se observa progreso conversacional con margen de mejora táctica. Ejemplo: {safe_excerpt}",
        evaluation_blocks=blocks,
        best_moment=KeyMoment(turn_index=safe_idx, why="Hubo señal de avance.", impact="Mejoró la alineación."),
        most_delicate_moment=KeyMoment(turn_index=safe_idx, why="Faltó precisión.", impact="Generó ambigüedad."),
        turning_point=KeyMoment(turn_index=safe_idx, why="Cambio de tono negociador.", impact="Reorientó la conversación."),
        recommendations=[
            {
                "title": "Conecta propuesta y criterio de legitimidad",
                "description": "Explicita qué principio respalda tu propuesta y qué contrapartida concreta esperas para avanzar de forma sostenible.",
                "example": {
                    "original_excerpt": safe_excerpt,
                    "better_rephrase": "Para mantener un acuerdo justo, propongo X por Y. ¿Qué ajuste haría esto viable para ambos?",
                },
            }
        ],
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
