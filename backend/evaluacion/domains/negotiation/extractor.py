from __future__ import annotations

from sessions.state import SessionState

from .context_resolver import resolve_evaluation_context_from_session

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


def _pair_turns_from_history(state: SessionState) -> list[BundleTurn]:
    turns: list[BundleTurn] = []
    raw_history = state.history if isinstance(state.history, list) else []
    user_queue: list[str] = []

    for item in raw_history:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            user_queue.append(content)
            continue
        if role == "assistant" and user_queue:
            user_text = user_queue.pop(0)
            idx = len(turns) + 1
            turns.append(
                BundleTurn(turn_index=idx, turn_id=f"turn-{idx}", user_text=user_text, assistant_text=content)
            )
    return turns


def _build_stats(turns: list[BundleTurn]) -> ConversationStats:
    if not turns:
        return ConversationStats(turn_count=0, duration_seconds=0, user_avg_chars=0, assistant_avg_chars=0)

    user_total = sum(len(t.user_text) for t in turns)
    assistant_total = sum(len(t.assistant_text) for t in turns)
    turn_count = len(turns)
    return ConversationStats(
        turn_count=turn_count,
        duration_seconds=turn_count * 30,
        user_avg_chars=int(user_total / turn_count),
        assistant_avg_chars=int(assistant_total / turn_count),
    )


def _build_domain_context(state: SessionState) -> DomainContext:
    canonical = state.world_state.get("negotiation_canonical", {}) if isinstance(state.world_state, dict) else {}
    planner_state = canonical.get("planner_state", {}) if isinstance(canonical, dict) else {}
    ui_state = canonical.get("ui_state", {}) if isinstance(canonical, dict) else {}
    phase = planner_state.get("current_phase") if isinstance(planner_state, dict) else None
    armed = bool(ui_state.get("finish_button_armed", False)) if isinstance(ui_state, dict) else False
    evaluation_context = resolve_evaluation_context_from_session(state)
    return DomainContext(
        domain="negociacion",
        flow_id=evaluation_context.flow_id,
        context_id=evaluation_context.context_id,
        context_version=evaluation_context.context_version,
        final_phase=str(phase) if phase else None,
        finish_button_was_armed=armed,
    )


def _build_derived_facts(turns: list[BundleTurn]) -> DerivedFacts:
    question_turns: list[int] = []
    close_signals = 0
    offer_signals = 0
    blocker_signals = 0

    for turn in turns:
        u = turn.user_text.lower()
        if "?" in turn.user_text:
            question_turns.append(turn.turn_index)
        if any(token in u for token in ("cerr", "acuerdo", "trato", "hoy")):
            close_signals += 1
        if any(token in u for token in ("precio", "ofert", "euros", "rebaja")):
            offer_signals += 1
        if any(token in u for token in ("no puedo", "imposible", "bloque", "difícil")):
            blocker_signals += 1

    return DerivedFacts(
        question_turn_indexes=question_turns,
        close_signals_count=close_signals,
        offer_signals_count=offer_signals,
        blocker_signals_count=blocker_signals,
    )


def _build_trace_digest(state: SessionState) -> TraceDigest:
    traces_key = "negotiation_canonical_traces"
    raw_traces = state.world_state.get(traces_key, []) if isinstance(state.world_state, dict) else []
    traces = raw_traces if isinstance(raw_traces, list) else []

    guardrail_events = 0
    for trace in traces:
        if isinstance(trace, dict) and trace.get("guardrails_triggered"):
            guardrail_events += 1
    return TraceDigest(trace_count=len(traces), guardrail_events_count=guardrail_events)


def build_feedback_input_bundle_v1(*, state: SessionState, evaluation_id: str) -> FeedbackInputBundleV1:
    turns = _pair_turns_from_history(state)
    return FeedbackInputBundleV1(
        schema_version="feedback_input_bundle.v1",
        evaluation_id=evaluation_id,
        session_ref=SessionRef(user_id=state.user_id, session_id=state.session_id),
        conversation=ConversationBlock(turns=turns),
        conversation_stats=_build_stats(turns),
        domain_context=_build_domain_context(state),
        derived_facts=_build_derived_facts(turns),
        trace_digest=_build_trace_digest(state),
    )
