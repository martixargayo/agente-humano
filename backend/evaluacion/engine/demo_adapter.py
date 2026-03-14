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
from evaluacion.dev_fixtures.models import FeedbackDemoFixtureV1


def fixture_to_bundle(*, fixture: FeedbackDemoFixtureV1, evaluation_id: str) -> FeedbackInputBundleV1:
    turns = [
        BundleTurn(
            turn_index=t.turn_index,
            turn_id=t.turn_id,
            user_text=t.user_text,
            assistant_text=t.assistant_text,
        )
        for t in fixture.conversation.turns
    ]

    turn_count = len(turns)
    user_avg = int(sum(len(t.user_text) for t in turns) / turn_count) if turn_count else 0
    assistant_avg = int(sum(len(t.assistant_text) for t in turns) / turn_count) if turn_count else 0

    overrides = fixture.derived_facts_overrides
    questions = [t.turn_index for t in turns if "?" in t.user_text]
    close_signals = sum(1 for t in turns if any(x in t.user_text.lower() for x in ("cerr", "acuerdo", "hoy")))
    offer_signals = sum(1 for t in turns if any(x in t.user_text.lower() for x in ("precio", "euros", "oferta", "rebaja")))
    blocker_signals = sum(1 for t in turns if any(x in t.user_text.lower() for x in ("no puedo", "imposible", "difícil", "bloque")))

    return FeedbackInputBundleV1(
        schema_version="feedback_input_bundle.v1",
        evaluation_id=evaluation_id,
        session_ref=SessionRef(user_id="dev_fixture", session_id=fixture.fixture_id),
        conversation=ConversationBlock(turns=turns),
        conversation_stats=ConversationStats(
            turn_count=turn_count,
            duration_seconds=fixture.conversation_stats.duration_seconds or turn_count * 30,
            user_avg_chars=user_avg,
            assistant_avg_chars=assistant_avg,
        ),
        domain_context=DomainContext(
            domain="negociacion",
            final_phase=fixture.domain_context.final_phase,
            finish_button_was_armed=fixture.domain_context.finish_button_was_armed,
        ),
        derived_facts=DerivedFacts(
            question_turn_indexes=overrides.question_turn_indexes if overrides and overrides.question_turn_indexes is not None else questions,
            close_signals_count=overrides.close_signals_count if overrides and overrides.close_signals_count is not None else close_signals,
            offer_signals_count=overrides.offer_signals_count if overrides and overrides.offer_signals_count is not None else offer_signals,
            blocker_signals_count=overrides.blocker_signals_count if overrides and overrides.blocker_signals_count is not None else blocker_signals,
        ),
        trace_digest=TraceDigest(
            trace_count=fixture.trace_digest.trace_count if fixture.trace_digest else 0,
            guardrail_events_count=fixture.trace_digest.guardrail_events_count if fixture.trace_digest else 0,
        ),
    )
