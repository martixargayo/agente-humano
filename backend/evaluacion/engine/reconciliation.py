from __future__ import annotations

import logging

from evaluacion.contracts.models import FeedbackReportCoreV1, TurnTrajectoryV1
from evaluacion.engine.flow_config import RECONCILE_SCORE_TOLERANCE

logger = logging.getLogger(__name__)


def reconcile_outputs(
    *,
    core: FeedbackReportCoreV1,
    trajectory: TurnTrajectoryV1,
    turn_count: int,
    context_id: str | None = None,
) -> TurnTrajectoryV1:
    expected = turn_count
    actual = len(trajectory.trajectory)
    if expected > 0 and actual == 0:
        raise ValueError("reconciliation_empty_trajectory")
    if expected > 0 and abs(expected - actual) > max(1, int(expected * 0.1)):
        raise ValueError("reconciliation_invalid_trajectory_cardinality")

    block_scores = [block.score_0_100 for block in core.evaluation_blocks]
    computed_global = round(sum(block_scores) / len(block_scores))
    original_global = core.score_global_100
    diff = abs(original_global - computed_global)
    if diff > RECONCILE_SCORE_TOLERANCE:
        logger.warning(
            "reconciliation_global_adjusted original_global=%s computed_global=%s diff=%.1f tolerance=%s",
            original_global,
            computed_global,
            diff,
            RECONCILE_SCORE_TOLERANCE,
        )
    core.score_global_100 = computed_global

    if not trajectory.trajectory:
        return trajectory

    conviction = trajectory.conviction_level_0_100
    if conviction is None:
        conviction = int(trajectory.trajectory[-1].agreement_closeness_score_0_100)

    if context_id == "conversacion-dificil-periodista":
        if core.interaction_outcome == "agreement_reached":
            conviction = max(conviction, 75)
        else:
            conviction = min(conviction, 74)

    conviction = max(1, min(100, int(conviction)))
    updated_rows = list(trajectory.trajectory)
    updated_rows[-1] = updated_rows[-1].model_copy(update={"agreement_closeness_score_0_100": conviction})
    return trajectory.model_copy(update={"trajectory": updated_rows, "conviction_level_0_100": conviction})
