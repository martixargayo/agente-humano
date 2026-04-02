from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from sessions.state import get_session_store, reset_session_store


class InterfazUsuarioTurnErrorHandlingTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_session_store()
        get_session_store().clear()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        reset_session_store()
        get_session_store().clear()

    def test_turn_returns_structured_500_when_pipeline_fails(self) -> None:
        bootstrap = self.client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_diag", "session_id": "s_diag"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        with patch("interfaz_usuario.services.execute_turn_with_contract", side_effect=RuntimeError("boom")):
            turn = self.client.post(
                "/api/interfaz_usuario/negociacion/turn",
                json={
                    "user_id": "u_diag",
                    "session_id": "s_diag",
                    "message": "hola",
                    "new_conversation": False,
                },
            )

        self.assertEqual(turn.status_code, 500)
        payload = turn.json()
        detail = payload.get("detail", {})
        self.assertEqual(detail.get("error"), "turn_execution_failed")
        self.assertIn("No se pudo procesar el turno", detail.get("message", ""))
        self.assertTrue(str(detail.get("error_id", "")).startswith("iu_turn_"))
        self.assertEqual(detail.get("cause"), "RuntimeError")
        self.assertIn("boom", detail.get("diagnostic", ""))
        self.assertEqual(detail.get("error_category"), "internal_turn_failure")
        self.assertFalse(detail.get("retryable"))

    def test_post_execution_ttl_timeout_does_not_fail_interfaz_turn(self) -> None:
        bootstrap = self.client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_diag_ttl", "session_id": "s_diag_ttl"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        def fake_execute(*, state, user_message, config, contract, turn_context=None):
            _ = (contract, turn_context)
            traces = state.world_state.setdefault("negotiation_canonical_traces", [])
            traces.append({"turn_id": "t1", "final_reply_text": f"ok::{user_message}", "logs": []})
            return f"ok::{user_message}", state, {
                "entry_contract": {
                    "entry_surface": "interfaz_usuario",
                    "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                    "overrides_applied": False,
                    "optimizer_wrapper_used": False,
                    "new_conversation": False,
                    "clone_used": False,
                    "config_snapshot": {
                        "memory_key": config.memory_key,
                        "thread_mode_default": str(config.thread_mode_default),
                        "model_memory": config.model_memory,
                        "model_phase_classifier": config.model_phase_classifier,
                        "model_planner": config.model_planner,
                        "model_executor": config.model_executor,
                        "max_recent_messages": config.max_recent_messages,
                        "max_executor_recent_turns": config.max_executor_recent_turns,
                    },
                },
                "trace_count": len(traces),
                "latest_turn_id": "t1",
            }

        def flaky_apply_ttl(state, *, scope, reason, persist=True):
            _ = (state, scope, persist)
            if reason == "interfaz_usuario_turn_completed":
                raise RuntimeError("Timeout writing to socket")
            return 120

        with patch("interfaz_usuario.services.execute_turn_with_contract", side_effect=fake_execute), patch(
            "interfaz_usuario.services.apply_session_ttl", side_effect=flaky_apply_ttl
        ):
            turn = self.client.post(
                "/api/interfaz_usuario/negociacion/turn",
                json={
                    "user_id": "u_diag_ttl",
                    "session_id": "s_diag_ttl",
                    "message": "hola",
                    "new_conversation": False,
                },
            )

        self.assertEqual(turn.status_code, 200)
        self.assertIn("post_commit_housekeeping_error", turn.json())

    def test_state_ready_ttl_is_not_called_in_interfaz_turn(self) -> None:
        bootstrap = self.client.post(
            "/api/interfaz_usuario/sessions/bootstrap",
            json={"user_id": "u_diag_ttl_eff", "session_id": "s_diag_ttl_eff"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        def fake_execute(*, state, user_message, config, contract, turn_context=None):
            _ = (contract, turn_context)
            traces = state.world_state.setdefault("negotiation_canonical_traces", [])
            traces.append({"turn_id": "t1", "final_reply_text": f"ok::{user_message}", "logs": []})
            return f"ok::{user_message}", state, {
                "entry_contract": {
                    "entry_surface": "interfaz_usuario",
                    "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                    "overrides_applied": False,
                    "optimizer_wrapper_used": False,
                    "new_conversation": False,
                    "clone_used": False,
                    "config_snapshot": {
                        "memory_key": config.memory_key,
                        "thread_mode_default": str(config.thread_mode_default),
                        "model_memory": config.model_memory,
                        "model_phase_classifier": config.model_phase_classifier,
                        "model_planner": config.model_planner,
                        "model_executor": config.model_executor,
                        "max_recent_messages": config.max_recent_messages,
                        "max_executor_recent_turns": config.max_executor_recent_turns,
                    },
                },
                "trace_count": len(traces),
                "latest_turn_id": "t1",
            }

        calls: list[tuple[str, bool]] = []

        def fake_apply_ttl(state, *, scope, reason, persist=True):
            _ = (state, scope)
            calls.append((reason, persist))
            return 120

        with patch("interfaz_usuario.services.execute_turn_with_contract", side_effect=fake_execute), patch(
            "interfaz_usuario.services.apply_session_ttl", side_effect=fake_apply_ttl
        ):
            turn = self.client.post(
                "/api/interfaz_usuario/negociacion/turn",
                json={
                    "user_id": "u_diag_ttl_eff",
                    "session_id": "s_diag_ttl_eff",
                    "message": "hola",
                    "new_conversation": False,
                },
            )
        self.assertEqual(turn.status_code, 200)
        self.assertTrue(all(reason != "interfaz_usuario_turn_state_ready" for reason, _ in calls))
