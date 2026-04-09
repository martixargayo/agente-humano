from __future__ import annotations

from evaluacion.domains.common_extractor import build_conversation_stats, pair_turns_from_history
from sessions.state import SessionState


def test_pair_turns_ignores_orphan_assistant_messages() -> None:
    state = SessionState(user_id='u', session_id='s')
    state.history = [
        {'role': 'assistant', 'content': 'hola'},
        {'role': 'user', 'content': 'u1'},
        {'role': 'assistant', 'content': 'a1'},
        {'role': 'assistant', 'content': 'a2'},
        {'role': 'user', 'content': 'u2'},
    ]

    turns = pair_turns_from_history(state)

    assert len(turns) == 1
    assert turns[0].user_text == 'u1'
    assert turns[0].assistant_text == 'a1'


def test_build_stats_zero_turns_safe_defaults() -> None:
    stats = build_conversation_stats([])

    assert stats.turn_count == 0
    assert stats.user_avg_chars == 0
    assert stats.assistant_avg_chars == 0
