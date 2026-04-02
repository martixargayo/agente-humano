from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from sessions.state import get_session_state, get_session_store, reset_session_store


class OptimizadorTurnErrorHandlingTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_session_store()
        get_session_store().clear()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self) -> None:
        reset_session_store()
        get_session_store().clear()

    def test_turn_returns_structured_500_when_pipeline_fails(self) -> None:
        bootstrap = self.client.post(
            "/api/optimizador/sessions/bootstrap",
            json={"user_id": "u_diag_opt", "session_id": "s_diag_opt"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        with patch("negociacion.optimizador.services.execute_turn_with_contract", side_effect=RuntimeError("boom")):
            turn = self.client.post(
                "/api/optimizador/sandbox/turn",
                json={
                    "optimizer_session_id": "default",
                    "user_id": "u_diag_opt",
                    "session_id": "s_diag_opt",
                    "message": "hola",
                },
            )

        self.assertEqual(turn.status_code, 500)
        payload = turn.json()
        detail = payload.get("detail", {})
        self.assertEqual(detail.get("error"), "turn_execution_failed")
        self.assertIn("No se pudo procesar el turno", detail.get("message", ""))
        self.assertTrue(str(detail.get("error_id", "")).startswith("opt_turn_"))
        self.assertEqual(detail.get("cause"), "RuntimeError")
        self.assertIn("boom", detail.get("diagnostic", ""))
        self.assertEqual(detail.get("error_category"), "internal_turn_failure")
        self.assertFalse(detail.get("retryable"))
        self.assertEqual(detail.get("failing_stage"), "execute_turn_with_contract")

    def test_turn_marks_socket_write_timeout_as_retryable(self) -> None:
        bootstrap = self.client.post(
            "/api/optimizador/sessions/bootstrap",
            json={"user_id": "u_diag_opt_timeout", "session_id": "s_diag_opt_timeout"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        with patch(
            "negociacion.optimizador.services.execute_turn_with_contract",
            side_effect=RuntimeError("Timeout writing to socket"),
        ):
            turn = self.client.post(
                "/api/optimizador/sandbox/turn",
                json={
                    "optimizer_session_id": "default",
                    "user_id": "u_diag_opt_timeout",
                    "session_id": "s_diag_opt_timeout",
                    "message": "hola",
                },
            )

        self.assertEqual(turn.status_code, 500)
        detail = turn.json().get("detail", {})
        self.assertEqual(detail.get("error_category"), "upstream_write_timeout")
        self.assertTrue(detail.get("retryable"))
        self.assertEqual(detail.get("failing_stage"), "execute_turn_with_contract")

    def test_turn_marks_session_storage_timeout_stage_and_category(self) -> None:
        bootstrap = self.client.post(
            "/api/optimizador/sessions/bootstrap",
            json={"user_id": "u_diag_opt_store", "session_id": "s_diag_opt_store"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        with patch(
            "negociacion.optimizador.services.touch_existing_session_if_present",
            side_effect=RuntimeError("Timeout writing to socket"),
        ):
            turn = self.client.post(
                "/api/optimizador/sandbox/turn",
                json={
                    "optimizer_session_id": "default",
                    "user_id": "u_diag_opt_store",
                    "session_id": "s_diag_opt_store",
                    "message": "hola",
                    "client_request_id": "req-123",
                },
            )

        self.assertEqual(turn.status_code, 500)
        detail = turn.json().get("detail", {})
        self.assertEqual(detail.get("error_category"), "session_storage_write_timeout")
        self.assertTrue(detail.get("retryable"))
        self.assertEqual(detail.get("failing_stage"), "touch_existing_session_if_present")
        self.assertEqual(detail.get("client_request_id"), "req-123")

    def test_post_execution_ttl_timeout_does_not_fail_turn_or_force_retry_cascade(self) -> None:
        bootstrap = self.client.post(
            "/api/optimizador/sessions/bootstrap",
            json={"user_id": "u_cost_diag", "session_id": "s_cost_diag"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        attempt_counter = {"n": 0}

        def fake_execute(*, state, user_message, config, contract, turn_context=None):
            _ = (contract, turn_context)
            traces = state.world_state.setdefault("negotiation_canonical_traces", [])
            idx = len(traces) + 1
            traces.append(
                {
                    "turn_id": f"t_{idx}",
                    "final_reply_text": f"ok::{user_message}",
                    "logs": [
                        {"node_name": "memory", "model_called": True},
                        {"node_name": "phase_classifier", "model_called": True},
                        {"node_name": "planner", "model_called": True},
                        {"node_name": "executor", "model_called": True},
                    ],
                }
            )
            return f"ok::{user_message}", state, {"entry_contract": {}, "trace_count": len(traces), "latest_turn_id": f"t_{idx}"}

        def flaky_apply_ttl(state, *, scope, reason, persist=True):
            _ = (state, scope, persist)
            if reason == "optimizador_turn_completed":
                attempt_counter["n"] += 1
                if attempt_counter["n"] < 3:
                    raise RuntimeError("Timeout writing to socket")
            return 120

        with patch("negociacion.optimizador.services.execute_turn_with_contract", side_effect=fake_execute), patch(
            "negociacion.optimizador.services.apply_session_ttl", side_effect=flaky_apply_ttl
        ):
            response = self.client.post(
                "/api/optimizador/sandbox/turn",
                json={
                    "optimizer_session_id": "default",
                    "user_id": "u_cost_diag",
                    "session_id": "s_cost_diag",
                    "message": "mensaje caro",
                    "logical_user_message_id": "lmsg_1",
                    "logical_attempt_index": 1,
                    "client_request_id": "req-1",
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("post_commit_housekeeping_error", response.json())

        attempts = self.client.get("/api/optimizador/sessions/u_cost_diag/s_cost_diag/attempts").json()["items"]
        logical_attempts = [item for item in attempts if item.get("logical_user_message_id") == "lmsg_1"]
        self.assertEqual(len(logical_attempts), 1)
        self.assertEqual(logical_attempts[0]["status"], "success_with_housekeeping_error")
        self.assertEqual(sum(int(item.get("model_calls_in_latest_trace", 0)) for item in logical_attempts), 4)
        state = get_session_state(user_id="u_cost_diag", session_id="s_cost_diag")
        self.assertEqual(len(state.world_state.get("negotiation_canonical_traces", [])), 1)

    def test_state_ready_ttl_is_not_called_to_reduce_session_store_writes(self) -> None:
        bootstrap = self.client.post(
            "/api/optimizador/sessions/bootstrap",
            json={"user_id": "u_ttl_eff", "session_id": "s_ttl_eff"},
        )
        self.assertEqual(bootstrap.status_code, 200)

        def fake_execute(*, state, user_message, config, contract, turn_context=None):
            _ = (contract, turn_context)
            traces = state.world_state.setdefault("negotiation_canonical_traces", [])
            traces.append({"turn_id": "t1", "final_reply_text": user_message, "logs": []})
            return user_message, state, {"entry_contract": {}, "trace_count": len(traces), "latest_turn_id": "t1"}

        calls: list[tuple[str, bool]] = []

        def fake_apply_ttl(state, *, scope, reason, persist=True):
            _ = (state, scope)
            calls.append((reason, persist))
            return 120

        with patch("negociacion.optimizador.services.execute_turn_with_contract", side_effect=fake_execute), patch(
            "negociacion.optimizador.services.apply_session_ttl", side_effect=fake_apply_ttl
        ):
            turn = self.client.post(
                "/api/optimizador/sandbox/turn",
                json={
                    "optimizer_session_id": "default",
                    "user_id": "u_ttl_eff",
                    "session_id": "s_ttl_eff",
                    "message": "hola",
                },
            )
        self.assertEqual(turn.status_code, 200)
        self.assertTrue(all(reason != "optimizador_turn_state_ready" for reason, _ in calls))
