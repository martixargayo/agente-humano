from __future__ import annotations

import unittest

from fastapi import HTTPException

from comunicacion.contexts import (
    COMMUNICATION_CONTEXT_WORLD_STATE_KEY,
    ensure_communication_session_context,
    read_bound_communication_context_from_session,
)
from sessions.state import SessionState


class ComunicacionContextBindingTests(unittest.TestCase):
    def test_context_is_bound_to_session(self) -> None:
        state = SessionState(user_id='u_ctx', session_id='s_ctx')
        bound = ensure_communication_session_context(state=state)

        self.assertEqual(bound.context_id, 'baseline_current')
        self.assertEqual(state.world_state[COMMUNICATION_CONTEXT_WORLD_STATE_KEY]['flow_id'], 'comunicacion')
        self.assertEqual(read_bound_communication_context_from_session(state).context_id, 'baseline_current')

    def test_valid_existing_binding_is_not_overwritten(self) -> None:
        state = SessionState(user_id='u_ctx', session_id='s_ctx')
        first = ensure_communication_session_context(state=state, requested_context_id='baseline_current')
        second = ensure_communication_session_context(state=state, requested_context_id='baseline_current')

        self.assertEqual(first.context_id, second.context_id)
        self.assertEqual(state.world_state[COMMUNICATION_CONTEXT_WORLD_STATE_KEY]['context_id'], 'baseline_current')

    def test_conflict_if_session_reused_with_incompatible_context(self) -> None:
        state = SessionState(user_id='u_ctx', session_id='s_ctx')
        ensure_communication_session_context(state=state, requested_context_id='baseline_current')

        with self.assertRaises(HTTPException) as ctx:
            ensure_communication_session_context(state=state, requested_context_id='otro_contexto')

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail['error'], 'session_context_conflict')
