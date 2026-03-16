from __future__ import annotations

from evaluacion.contracts.models import (
    BundleTurn,
    ConversationBlock,
    ConversationStats,
    DerivedFacts,
    DomainContext,
    FeedbackInputBundleV1,
    SessionRef,
    TraceDigest,
)
from evaluacion.engine.input_shaping import shape_core_input, shape_trajectory_input


def test_shape_inputs_preserve_dialogue_priority_and_basic_constraints() -> None:
    turns = [
        BundleTurn(turn_index=i, turn_id=f"turn-{i}", user_text="u" * 20, assistant_text="a" * 20)
        for i in range(1, 6)
    ]
    bundle = FeedbackInputBundleV1(
        schema_version="feedback_input_bundle.v1",
        evaluation_id="ev-1",
        session_ref=SessionRef(user_id="u1", session_id="s1"),
        conversation=ConversationBlock(turns=turns),
        conversation_stats=ConversationStats(turn_count=5, duration_seconds=100, user_avg_chars=20, assistant_avg_chars=20),
        domain_context=DomainContext(domain="negociacion", final_phase=None, finish_button_was_armed=False),
        derived_facts=DerivedFacts(question_turn_indexes=[1, 2], close_signals_count=1, offer_signals_count=2, blocker_signals_count=0),
        trace_digest=TraceDigest(trace_count=2, guardrail_events_count=0),
    )

    core = shape_core_input(bundle)
    trajectory = shape_trajectory_input(bundle)

    assert core.schema_version == "core_runner_input.v1"
    assert trajectory.schema_version == "trajectory_runner_input.v1"
    assert len(core.conversation.turns) == 5
    assert len(trajectory.turns_for_trajectory) == 5
    assert "derived_facts" not in core.model_dump()
    assert "trace_digest" not in core.model_dump()
    assert "derived_facts" not in trajectory.model_dump()
    assert "trace_digest" not in trajectory.model_dump()
