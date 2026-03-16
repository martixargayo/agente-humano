from __future__ import annotations

import pytest

from evaluacion.contracts.models import (
    EvaluationBlock,
    EvaluationCheck,
    FeedbackReportCoreV1,
    KeyMoment,
    RecommendationItem,
)
from evaluacion.domains.negotiation import load_negotiation_rubric_v1
from evaluacion.engine.validators import validate_core_business


def test_negotiation_rubric_loader_returns_expected_blocks() -> None:
    rubric = load_negotiation_rubric_v1()
    assert rubric.schema_version == "negotiation_domain_rubric.v1"
    assert [block.block_id for block in rubric.blocks] == ["valores", "vision", "relacion", "proceso"]
    assert rubric.global_guide.principles


def test_core_validation_requires_new_block_taxonomy() -> None:
    check = EvaluationCheck(polarity="check", micro_explanation="ok", evidence_turn_indexes=[1])
    km = KeyMoment(turn_index=1, why="w", impact="i")
    core = FeedbackReportCoreV1(
        schema_version="feedback_report_core.v1",
        score_global_100=65,
        interaction_outcome="partial_progress",
        summary_2_3_lines="s",
        evaluation_blocks=[
            EvaluationBlock(block_id="valores", title="Valores", status_visual="mejorable", score_0_100=65, checks=[check], block_verdict="v"),
            EvaluationBlock(block_id="vision", title="Visión", status_visual="mejorable", score_0_100=65, checks=[check], block_verdict="v"),
            EvaluationBlock(block_id="relacion", title="Relación", status_visual="mejorable", score_0_100=65, checks=[check], block_verdict="v"),
            EvaluationBlock(block_id="proceso", title="Proceso", status_visual="mejorable", score_0_100=65, checks=[check], block_verdict="v"),
        ],
        best_moment=km,
        most_delicate_moment=km,
        turning_point=km,
        recommendations=[RecommendationItem(title="t", description="d", example=None)],
    )

    validate_core_business(core, turn_indexes={1})

    invalid = core.model_copy(update={"evaluation_blocks": core.evaluation_blocks[:-1] + [core.evaluation_blocks[0]]})
    with pytest.raises(ValueError, match="core_invalid_block_ids"):
        validate_core_business(invalid, turn_indexes={1})
