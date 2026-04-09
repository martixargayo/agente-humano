from __future__ import annotations

from sessions.state import SessionState

from evaluacion.contracts.models import BundleTurn, ConversationStats


def pair_turns_from_history(state: SessionState) -> list[BundleTurn]:
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
            turns.append(BundleTurn(turn_index=idx, turn_id=f"turn-{idx}", user_text=user_text, assistant_text=content))
    return turns


def build_conversation_stats(turns: list[BundleTurn]) -> ConversationStats:
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
