from __future__ import annotations

import pytest

from evaluacion.contracts.models import (
    CorrectionCase,
    EvaluationBlock,
    EvaluationCheck,
    FeedbackReportCoreV1,
    KeyMoment,
    TrajectoryTurn,
    TurnTrajectoryV1,
)
from evaluacion.engine.reconciliation import reconcile_outputs


def _core(score: int = 70) -> FeedbackReportCoreV1:
    block = EvaluationBlock(
        block_id="comprension_exploracion",
        title="x",
        status_visual="mejorable",
        score_0_100=score,
        checks=[EvaluationCheck(polarity="check", micro_explanation="ok", evidence_turn_indexes=[1])],
        block_verdict="v",
    )
    blocks = [
        block,
        block.model_copy(update={"block_id": "comunicacion_clima"}),
        block.model_copy(update={"block_id": "movimiento_tactico"}),
        block.model_copy(update={"block_id": "cierre_avance"}),
    ]
    km = KeyMoment(turn_index=1, why="w", impact="i")
    return FeedbackReportCoreV1(
        schema_version="feedback_report_core.v1",
        score_global_100=score,
        stars_0_5=3.5,
        interaction_outcome="partial_progress",
        summary_2_3_lines="s",
        evaluation_blocks=blocks,
        best_moment=km,
        most_delicate_moment=km,
        turning_point=km,
        recommendations_general=["g"],
        correction_cases=[CorrectionCase(turn_index=1, original_excerpt="o", better_rephrase="b", expected_effect="e")],
        strengths_to_repeat=["st"],
        next_focus="n",
        recommended_closing_phrase="c",
    )


def test_reconciliation_fails_on_invalid_trajectory_cardinality() -> None:
    core = _core()
    traj = TurnTrajectoryV1(
        schema_version="turn_trajectory.v1",
        trajectory=[],
        trend_label="flat",
        largest_drop_turn_index=1,
        largest_gain_turn_index=1,
    )
    with pytest.raises(ValueError):
        reconcile_outputs(core=core, trajectory=traj, turn_count=3)


def test_reconciliation_recomputes_gain_drop_indexes() -> None:
    core = _core(score=68)
    traj = TurnTrajectoryV1(
        schema_version="turn_trajectory.v1",
        trajectory=[
            TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=40, delta_vs_previous=0, direction="flat", user_excerpt="u", counterpart_excerpt="a", impact_reason="i", counterpart_thought_effect="t", better_rephrase="b"),
            TrajectoryTurn(turn_index=2, agreement_closeness_score_0_100=50, delta_vs_previous=10, direction="up", user_excerpt="u", counterpart_excerpt="a", impact_reason="i", counterpart_thought_effect="t", better_rephrase="b"),
            TrajectoryTurn(turn_index=3, agreement_closeness_score_0_100=44, delta_vs_previous=-6, direction="down", user_excerpt="u", counterpart_excerpt="a", impact_reason="i", counterpart_thought_effect="t", better_rephrase="b"),
        ],
        trend_label="mixed",
        largest_drop_turn_index=1,
        largest_gain_turn_index=1,
    )
    reconciled = reconcile_outputs(core=core, trajectory=traj, turn_count=3)
    assert reconciled.largest_gain_turn_index == 2
    assert reconciled.largest_drop_turn_index == 3
