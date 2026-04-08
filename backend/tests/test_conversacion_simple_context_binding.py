from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.contexts import ensure_conversacion_simple_session_context, read_bound_conversacion_simple_context_from_session
from conversacion_simple.orchestration.context_errors import ConversationSimpleSessionContextConflictError
from sessions.state import SessionState


def test_bind_and_read_context_from_session() -> None:
    state = SessionState(user_id="u", session_id="s")
    bound = ensure_conversacion_simple_session_context(state=state, requested_context_id="baseline")
    assert bound.context_id == "baseline"

    reread = read_bound_conversacion_simple_context_from_session(state)
    assert reread is not None
    assert reread.context_id == "baseline"


def test_binding_conflict_raises() -> None:
    state = SessionState(user_id="u", session_id="s")
    ensure_conversacion_simple_session_context(state=state, requested_context_id="baseline")
    with pytest.raises(ConversationSimpleSessionContextConflictError):
        ensure_conversacion_simple_session_context(state=state, requested_context_id="negociacion_sala_reuniones")
