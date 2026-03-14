from __future__ import annotations

from evaluacion.contracts.models import (
    FeedbackReportCoreV1,
    KeyMomentsPanel,
    Provenance,
    RecommendationsPanel,
    TurnTrajectoryV1,
    UiFeedbackReportV1,
    UiHeader,
)


def assemble_ui_report(*, core: FeedbackReportCoreV1, trajectory: TurnTrajectoryV1, provenance: Provenance) -> UiFeedbackReportV1:
    return UiFeedbackReportV1(
        schema_version="ui_feedback_report.v1",
        evaluation_id=provenance.evaluation_id,
        header=UiHeader(
            report_title="Evaluación de tu desempeño",
            activity_name="Compra de un Mustang clásico",
            score_global_100=core.score_global_100,
            stars_0_5=core.stars_0_5,
            interaction_outcome=core.interaction_outcome,
            summary_2_3_lines=core.summary_2_3_lines,
        ),
        block_cards=core.evaluation_blocks,
        trajectory_chart=trajectory.trajectory,
        key_moments=KeyMomentsPanel(
            best_moment=core.best_moment,
            most_delicate_moment=core.most_delicate_moment,
            turning_point=core.turning_point,
        ),
        recommendations=RecommendationsPanel(
            general=core.recommendations_general,
            correction_cases=core.correction_cases,
        ),
        strengths=core.strengths_to_repeat,
        next_focus=core.next_focus,
        recommended_closing_phrase=core.recommended_closing_phrase,
        provenance=provenance,
    )
