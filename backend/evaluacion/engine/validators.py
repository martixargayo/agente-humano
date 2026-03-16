from __future__ import annotations

from evaluacion.contracts.models import FeedbackReportCoreV1, TurnTrajectoryV1

REQUIRED_BLOCK_IDS = {"valores", "vision", "relacion", "proceso"}


def validate_core_business(core: FeedbackReportCoreV1, *, turn_indexes: set[int]) -> None:
    if len(core.evaluation_blocks) != 4:
        raise ValueError("core_invalid_blocks_count")
    if not 0 <= core.score_global_100 <= 100:
        raise ValueError("core_invalid_score_global")

    seen_block_ids = {block.block_id for block in core.evaluation_blocks}
    if seen_block_ids != REQUIRED_BLOCK_IDS:
        raise ValueError("core_invalid_block_ids")

    for block in core.evaluation_blocks:
        if not 0 <= block.score_0_100 <= 100:
            raise ValueError("core_invalid_block_score")
        for check in block.checks:
            for idx in check.evidence_turn_indexes:
                if idx not in turn_indexes:
                    raise ValueError("core_invalid_evidence_turn_index")

    for moment in (core.best_moment, core.most_delicate_moment, core.turning_point):
        if moment.turn_index not in turn_indexes:
            raise ValueError("core_invalid_key_moment_turn")


def validate_trajectory_business(trajectory: TurnTrajectoryV1, *, turn_indexes: set[int]) -> None:
    if not trajectory.trajectory:
        raise ValueError("trajectory_empty")

    seen: set[int] = set()
    for item in trajectory.trajectory:
        if item.turn_index not in turn_indexes:
            raise ValueError("trajectory_invalid_turn_index")
        if item.turn_index in seen:
            raise ValueError("trajectory_duplicate_turn_index")
        seen.add(item.turn_index)
        if not 0 <= item.agreement_closeness_score_0_100 <= 100:
            raise ValueError("trajectory_score_out_of_range")
