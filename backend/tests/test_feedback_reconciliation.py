from __future__ import annotations

import pytest

from evaluacion.contracts.models import (
    EvaluationBlock,
    EvaluationCheck,
    FeedbackReportCoreV1,
    KeyMoment,
    RecommendationItem,
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
        interaction_outcome="partial_progress",
        summary_2_3_lines="s",
        evaluation_blocks=blocks,
        best_moment=km,
        most_delicate_moment=km,
        turning_point=km,
        recommendations=[RecommendationItem(title="t", description="d", example=None)],
    )


def test_reconciliation_fails_on_invalid_trajectory_cardinality() -> None:
    core = _core()
    traj = TurnTrajectoryV1(schema_version="turn_trajectory.v1", trajectory=[])
    with pytest.raises(ValueError):
        reconcile_outputs(core=core, trajectory=traj, turn_count=3)


def test_reconciliation_keeps_trajectory_payload() -> None:
    core = _core(score=68)
    traj = TurnTrajectoryV1(
        schema_version="turn_trajectory.v1",
        trajectory=[
            TrajectoryTurn(turn_index=1, agreement_closeness_score_0_100=40, user_excerpt="u", counterpart_excerpt="a", impact_reason="i", counterpart_thought_effect="t", better_rephrase=None),
            TrajectoryTurn(turn_index=2, agreement_closeness_score_0_100=50, user_excerpt="u", counterpart_excerpt="a", impact_reason="i", counterpart_thought_effect="t", better_rephrase="b"),
            TrajectoryTurn(turn_index=3, agreement_closeness_score_0_100=44, user_excerpt="u", counterpart_excerpt="a", impact_reason="i", counterpart_thought_effect="t", better_rephrase="b"),
        ],
    )
    reconciled = reconcile_outputs(core=core, trajectory=traj, turn_count=3)
    assert reconciled == traj
