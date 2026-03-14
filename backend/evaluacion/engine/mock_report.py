from __future__ import annotations

from evaluacion.contracts.models import BlockCard, BlockCheck, FeedbackInputBundleV1, ReportHeader, TrajectoryPoint, UiFeedbackReportV1


def _outcome_from_turns(turn_count: int) -> str:
    if turn_count >= 6:
        return "partial_progress"
    if turn_count >= 1:
        return "no_agreement"
    return "blocked"


def build_mock_ui_report(*, bundle: FeedbackInputBundleV1) -> UiFeedbackReportV1:
    score = 60 + min(bundle.turn_count, 20)
    score = max(0, min(score, 95))
    stars = round((score / 100) * 5, 1)

    blocks = [
        BlockCard(
            block_id="comprension_exploracion",
            title="Comprensión y exploración",
            status_visual="mejorable",
            score_0_100=max(score - 10, 0),
            checks=[BlockCheck(polarity="check", text="Se identificaron elementos de contexto en la conversación.")],
            verdict="Base presente, falta mayor profundidad en preguntas exploratorias.",
        ),
        BlockCard(
            block_id="comunicacion_clima",
            title="Comunicación y clima",
            status_visual="correcto" if bundle.turn_count >= 3 else "mejorable",
            score_0_100=score,
            checks=[BlockCheck(polarity="check", text="Tono conversacional mantenido en la mayoría de turnos.")],
            verdict="Comunicación funcional y utilizable para avanzar.",
        ),
        BlockCard(
            block_id="movimiento_tactico",
            title="Movimiento táctico",
            status_visual="mejorable",
            score_0_100=max(score - 5, 0),
            checks=[BlockCheck(polarity="cross", text="Faltan más movimientos de intercambio explícito.")],
            verdict="Necesita más claridad en concesiones y contrapartidas.",
        ),
        BlockCard(
            block_id="cierre_avance",
            title="Cierre y avance",
            status_visual="mejorable",
            score_0_100=max(score - 8, 0),
            checks=[BlockCheck(polarity="check", text="Existe intención de cierre, aún no consolidada.")],
            verdict="Se observa avance parcial sin cierre concluyente.",
        ),
    ]

    trajectory: list[TrajectoryPoint] = []
    current = 40
    for turn in bundle.conversation_turns:
        next_score = min(current + 4, 92)
        direction = "up" if next_score > current else "flat"
        trajectory.append(
            TrajectoryPoint(
                turn_index=turn.turn_index,
                agreement_closeness_score_0_100=next_score,
                direction=direction,
            )
        )
        current = next_score

    if not trajectory:
        trajectory = [TrajectoryPoint(turn_index=1, agreement_closeness_score_0_100=35, direction="flat")]

    return UiFeedbackReportV1(
        schema_version="ui_feedback_report.v1",
        evaluation_id=bundle.evaluation_id,
        header=ReportHeader(
            report_title="Informe de desempeño",
            activity_name="Negociación",
            score_global_100=score,
            stars_0_5=stars,
            interaction_outcome=_outcome_from_turns(bundle.turn_count),
        ),
        block_cards=blocks,
        trajectory_chart=trajectory,
        strengths=["Mantienes continuidad conversacional en la sesión."],
        next_focus="Formula preguntas más específicas antes de proponer cierre.",
        recommended_closing_phrase="Si te parece, cerramos con estas condiciones y confirmamos próximos pasos.",
        provenance={
            "report_mode": "mock_phase2",
            "bundle_schema_version": bundle.schema_version,
        },
    )
