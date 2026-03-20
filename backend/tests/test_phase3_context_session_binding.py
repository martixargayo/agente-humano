from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from interfaz_usuario import services
from negociacion.contexts import NEGOTIATION_CONTEXT_WORLD_STATE_KEY, read_bound_context_from_session
from sessions.state import SESSIONS, SessionState, get_session_state


class Phase3ContextSessionBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()

    def test_new_session_without_context_id_binds_default_official_baseline(self) -> None:
        payload = services.ensure_session(user_id="u_default", session_id="s_default")

        state = get_session_state(user_id="u_default", session_id="s_default")
        bound = read_bound_context_from_session(state)
        self.assertIsNotNone(bound)
        self.assertEqual(bound.flow_id, "negociacion")
        self.assertEqual(bound.context_id, "baseline_current")
        self.assertEqual(bound.context_version, "1.0.0")
        self.assertEqual(payload["conversation_id"], None)
        self.assertEqual(payload["previous_response_id"], None)

    def test_new_session_with_explicit_baseline_context_binds_requested_context(self) -> None:
        services.ensure_session(user_id="u_explicit", session_id="s_explicit", context_id="baseline_current")

        state = get_session_state(user_id="u_explicit", session_id="s_explicit")
        self.assertEqual(
            state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {
                "flow_id": "negociacion",
                "context_id": "baseline_current",
                "context_version": "1.0.0",
            },
        )

    def test_existing_session_reuses_same_bound_context(self) -> None:
        first_payload = services.ensure_session(user_id="u_reuse", session_id="s_reuse")

        first = get_session_state(user_id="u_reuse", session_id="s_reuse").world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY].copy()
        second_payload = services.ensure_session(user_id="u_reuse", session_id="s_reuse")
        second = get_session_state(user_id="u_reuse", session_id="s_reuse").world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY].copy()

        self.assertEqual(first, second)
        self.assertEqual(first_payload["session_bootstrap_state"], "new")
        self.assertFalse(first_payload["existing_session"])
        self.assertEqual(second_payload["session_bootstrap_state"], "rehydrated")
        self.assertTrue(second_payload["existing_session"])

    def test_existing_session_rebootstrap_with_different_context_is_rejected_without_silent_mix(self) -> None:
        services.ensure_session(user_id="u_conflict", session_id="s_conflict")
        state = get_session_state(user_id="u_conflict", session_id="s_conflict")
        before = state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY].copy()

        with self.assertRaises(HTTPException) as ctx:
            services.ensure_session(user_id="u_conflict", session_id="s_conflict", context_id="otro_contexto")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["error"], "session_context_conflict")
        self.assertEqual(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY], before)

    def test_new_conversation_inherits_context_id_and_context_version(self) -> None:
        services.ensure_session(user_id="u_newconv", session_id="s_base")

        created = services.create_new_conversation(user_id="u_newconv", base_session_id="s_base")
        derived_state = get_session_state(user_id="u_newconv", session_id=created["session_id"])

        self.assertNotEqual(created["session_id"], "s_base")
        self.assertEqual(
            derived_state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {
                "flow_id": "negociacion",
                "context_id": "baseline_current",
                "context_version": "1.0.0",
            },
        )

    def test_context_is_persisted_in_world_state(self) -> None:
        state = get_session_state(user_id="u_world", session_id="s_world")
        services.ensure_session(user_id="u_world", session_id="s_world")

        self.assertIn(NEGOTIATION_CONTEXT_WORLD_STATE_KEY, state.world_state)
        self.assertIsInstance(state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY], dict)

    def test_legacy_session_without_context_is_backfilled_to_baseline(self) -> None:
        legacy_state = SessionState(user_id="u_legacy", session_id="s_legacy")
        legacy_state.world_state["negotiation_canonical"] = {"openai_thread": {"conversation_id": "conv-1", "previous_response_id": "resp-1"}}
        SESSIONS[("u_legacy", "s_legacy")] = legacy_state

        payload = services.ensure_session(user_id="u_legacy", session_id="s_legacy")
        rebound = get_session_state(user_id="u_legacy", session_id="s_legacy")

        self.assertEqual(payload["conversation_id"], "conv-1")
        self.assertEqual(payload["previous_response_id"], "resp-1")
        self.assertEqual(
            rebound.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {
                "flow_id": "negociacion",
                "context_id": "baseline_current",
                "context_version": "1.0.0",
            },
        )

    def test_baseline_observable_session_behavior_stays_unchanged_when_binding_context(self) -> None:
        state = get_session_state(user_id="u_observable", session_id="s_observable")
        canonical = {
            "openai_thread": {"conversation_id": "conv-observable", "previous_response_id": "resp-observable"},
            "planner_state": {},
            "ui_state": {},
        }
        state.world_state["negotiation_canonical"] = canonical.copy()

        payload = services.ensure_session(user_id="u_observable", session_id="s_observable")

        self.assertEqual(payload["conversation_id"], "conv-observable")
        self.assertEqual(payload["previous_response_id"], "resp-observable")
        self.assertEqual(state.world_state["negotiation_canonical"], canonical)
        self.assertEqual(
            set(payload.keys()),
            {
                "user_id",
                "session_id",
                "trace_count",
                "last_updated",
                "session_bootstrap_state",
                "existing_session",
                "conversation_id",
                "previous_response_id",
                "context_id",
                "public_slug",
                "presentation_config",
            },
        )
        self.assertEqual(payload["session_bootstrap_state"], "rehydrated")
        self.assertTrue(payload["existing_session"])

    def test_run_turn_backfills_and_reuses_session_context_without_changing_turn_contract_surface(self) -> None:
        state = get_session_state(user_id="u_turn", session_id="s_turn")
        state.world_state["negotiation_canonical"] = {
            "openai_thread": {"conversation_id": "conv-before", "previous_response_id": "resp-before"},
            "planner_state": {"current_phase": "clima_humano"},
            "ui_state": {"finish_button_armed": False},
        }

        with patch("interfaz_usuario.services.build_negotiation_pipeline_config", return_value=object()), patch(
            "interfaz_usuario.services.execute_turn_with_contract",
            return_value=(
                "respuesta-controlada",
                state,
                {
                    "trace_count": 0,
                    "conversation_id_before": "conv-before",
                    "conversation_id_after": "conv-after",
                    "previous_response_id_before": "resp-before",
                    "previous_response_id_after": "resp-after",
                    "latest_turn_id": "turn-1",
                    "entry_contract": {
                        "entry_surface": "interfaz_usuario",
                        "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                        "overrides_applied": False,
                        "optimizer_wrapper_used": False,
                        "new_conversation": False,
                        "clone_used": False,
                        "config_snapshot": {
                            "memory_key": "negotiation_canonical",
                            "thread_mode_default": "conversation",
                            "model_memory": "m1",
                            "model_phase_classifier": "m2",
                            "model_planner": "m3",
                            "model_executor": "m4",
                            "max_recent_messages": 12,
                            "max_executor_recent_turns": 4,
                        },
                    },
                },
            ),
        ):
            result = services.run_turn(user_id="u_turn", session_id="s_turn", message="hola", new_conversation=False)

        self.assertEqual(result["session_id"], "s_turn")
        self.assertEqual(result["conversation_id_before"], "conv-before")
        self.assertEqual(result["previous_response_id_before"], "resp-before")
        self.assertEqual(result["reply"], "respuesta-controlada")
        self.assertEqual(
            state.world_state[NEGOTIATION_CONTEXT_WORLD_STATE_KEY],
            {
                "flow_id": "negociacion",
                "context_id": "baseline_current",
                "context_version": "1.0.0",
            },
        )


if __name__ == "__main__":
    unittest.main()
