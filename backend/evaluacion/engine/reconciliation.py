from __future__ import annotations

from evaluacion.contracts.models import FeedbackReportCoreV1, TurnTrajectoryV1
from evaluacion.engine.flow_config import RECONCILE_SCORE_TOLERANCE


def reconcile_outputs(*, core: FeedbackReportCoreV1, trajectory: TurnTrajectoryV1, turn_count: int) -> TurnTrajectoryV1:
    expected = turn_count
    actual = len(trajectory.trajectory)
    if expected > 0 and actual == 0:
        raise ValueError("reconciliation_empty_trajectory")
    if expected > 0 and abs(expected - actual) > max(1, int(expected * 0.1)):
        raise ValueError("reconciliation_invalid_trajectory_cardinality")

    mean_block_score = sum(block.score_0_100 for block in core.evaluation_blocks) / len(core.evaluation_blocks)
    if abs(core.score_global_100 - mean_block_score) > RECONCILE_SCORE_TOLERANCE:
        raise ValueError("reconciliation_global_vs_blocks_mismatch")

    gains = max(trajectory.trajectory, key=lambda t: t.delta_vs_previous)
    drops = min(trajectory.trajectory, key=lambda t: t.delta_vs_previous)
    return trajectory.model_copy(
        update={"largest_gain_turn_index": gains.turn_index, "largest_drop_turn_index": drops.turn_index}
    )
