from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from sessions.state import get_session_store, reset_session_store


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
