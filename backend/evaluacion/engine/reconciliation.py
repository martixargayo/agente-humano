from __future__ import annotations

from evaluacion.contracts.models import FeedbackReportCoreV1, TurnTrajectoryV1
from evaluacion.engine.flow_config import RECONCILE_SCORE_TOLERANCE


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

    mean_block_score = sum(block.score_0_100 for block in core.evaluation_blocks) / len(core.evaluation_blocks)
    if abs(core.score_global_100 - mean_block_score) > RECONCILE_SCORE_TOLERANCE:
        raise ValueError("reconciliation_global_vs_blocks_mismatch")

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
