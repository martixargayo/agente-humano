from __future__ import annotations

from evaluacion.contracts.models import (
    BundleTurn,
    CoreRunnerInputV1,
    FeedbackInputBundleV1,
    TrajectoryRunnerInputV1,
)
from evaluacion.engine.flow_config import MAX_TEXT_CHARS_PER_SIDE, MAX_TURNS_FOR_EVAL


def _trim(text: str) -> str:
    t = text.strip()
    if len(t) <= MAX_TEXT_CHARS_PER_SIDE:
        return t
    return f"{t[: MAX_TEXT_CHARS_PER_SIDE - 3]}..."


def _shape_turn(turn: BundleTurn) -> BundleTurn:
    return turn.model_copy(update={"user_text": _trim(turn.user_text), "assistant_text": _trim(turn.assistant_text)})


def _select_turns(turns: list[BundleTurn]) -> list[BundleTurn]:
    if len(turns) <= MAX_TURNS_FOR_EVAL:
        return turns
    head = turns[:4]
    tail = turns[-20:]
    middle_budget = MAX_TURNS_FOR_EVAL - len(head) - len(tail)
    middle = turns[4 : 4 + max(middle_budget, 0)]
    return [*head, *middle, *tail]


def shape_core_input(bundle: FeedbackInputBundleV1) -> CoreRunnerInputV1:
    selected = [_shape_turn(t) for t in _select_turns(bundle.conversation.turns)]
    return CoreRunnerInputV1(
        schema_version="core_runner_input.v1",
        evaluation_id=bundle.evaluation_id,
        conversation=bundle.conversation.model_copy(update={"turns": selected}),
        conversation_stats=bundle.conversation_stats,
        domain_context=bundle.domain_context,
    )


def shape_trajectory_input(bundle: FeedbackInputBundleV1) -> TrajectoryRunnerInputV1:
    selected = [_shape_turn(t) for t in _select_turns(bundle.conversation.turns)]
    return TrajectoryRunnerInputV1(
        schema_version="trajectory_runner_input.v1",
        evaluation_id=bundle.evaluation_id,
        turns_for_trajectory=selected,
    )
